"""Foundry クラウド評価(evals API)のクライアント側ロジック。

本ポートの独自価値: ループの各周回の中間出力(初稿 / 改訂1 / 改訂2)を
**azure-ai-projects の evals API(OpenAI 互換 evals クライアント)**で採点し、
「実行時の自己批評(critic の verdict)」と「オフラインのクラウド評価器の
スコア」の傾向が一致するかを突き合わせる。

実装前調査(azure-ai-projects 2.4.0 精読 — 採った経路は README 参照):
- ``AIProjectClient`` に evals 操作群は**ない**(あるのは evaluation_rules /
  datasets 等)。evals は ``client.get_openai_client()`` が返す **openai SDK
  クライアントの ``.evals``**(base_url = プロジェクトエンドポイント +
  /openai/v1、Entra bearer token provider 認証)として露出する。
- 組み込み評価器は openai ネイティブにない testing_criteria 型
  ``{"type": "azure_ai_evaluator", "evaluator_name": "builtin.*", ...}``
  (azure.ai.projects.models.TestingCriterionAzureAIEvaluator TypedDict)で
  指定する。openai SDK は TypedDict を実行時検証しないため dict のまま通る。
- rubric 評価は openai ネイティブの ``score_model`` グレーダー(モデル判定+
  自由記述 rubric)で行う — Azure 拡張でなくてもサーバー側で実行される。

このモジュールは **純ロジックのみ**(評価アイテムの組み立て・評価器定義・
結果集計)でネットワークを触らない。実行系(クライアント生成・ポーリング)
は scripts/run_cloud_eval.py にある。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

#: 評価対象の版(stage)。initial = 統合直後の初稿、revision-N = N 回目の改訂
STAGE_INITIAL = "initial"

#: 実行時の critic がその版に下した判断(クラウド評価スコアと突き合わせる)
RUNTIME_REVISE = "revise"  # 批評されて改訂された
RUNTIME_ACCEPT = "accept"  # 合格判定(早期終了)
RUNTIME_UNEVALUATED = "unevaluated"  # 上限打ち切りで実行時には未批評(最終改訂)

#: data_source_config("custom")の item スキーマ
ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "run_label": {"type": "string"},
        "prompt": {"type": "string"},
        "stage": {"type": "string"},
        "stage_index": {"type": "integer"},
        "answer": {"type": "string"},
        "runtime_verdict": {"type": "string"},
    },
    "required": ["prompt", "stage", "answer"],
}

#: rubric(score_model)のシステムプロンプト。実行時 critic が見る観点
#: (欠落・不明瞭・具体性)と同じ軸で 1〜5 を付けさせ、傾向を比較可能にする
RUBRIC_SYSTEM_PROMPT = (
    "You are grading the quality of an answer to a question. "
    "Score from 1 to 5 using this rubric:\n"
    "5 = complete, accurate, clearly explained, with concrete examples where helpful\n"
    "4 = solid answer with only minor gaps or minor clarity issues\n"
    "3 = adequate but missing notable information or partially unclear\n"
    "2 = significant gaps, unclear explanations, or likely errors\n"
    "1 = mostly incorrect, off-topic, or unusable\n"
    "Respond with only the score."
)

RUBRIC_USER_TEMPLATE = "Question: {{item.prompt}}\n\nAnswer to grade:\n{{item.answer}}"


def build_eval_items(run: dict[str, Any], run_label: str = "") -> list[dict[str, Any]]:
    """CLI ``--save-run`` の実行結果 JSON から、版(stage)ごとの評価アイテム
    を組み立てる。

    実行時 verdict の対応付け:
    - 初稿・途中の改訂: critic に批評されて改訂された → "revise"
    - 最終版: 早期終了なら "accept"、上限打ち切りなら "unevaluated"
      (**元実装も移植も、上限到達時の最終改訂は実行時には批評されない** —
      そこを補完するのがオフラインのクラウド評価、という役割分担)
    """
    prompt = run["prompt"]
    revisions = run.get("revisions", [])
    stop_reason = run.get("stop_reason", "")
    final_verdict = RUNTIME_ACCEPT if stop_reason == "accepted" else RUNTIME_UNEVALUATED

    versions: list[tuple[str, str]] = [(STAGE_INITIAL, run["initial_answer"])]
    versions.extend((f"revision-{rev['round']}", rev["answer"]) for rev in revisions)

    items = []
    last = len(versions) - 1
    for index, (stage, answer) in enumerate(versions):
        items.append(
            {
                "run_label": run_label,
                "prompt": prompt,
                "stage": stage,
                "stage_index": index,
                "answer": answer,
                "runtime_verdict": final_verdict if index == last else RUNTIME_REVISE,
            }
        )
    return items


def build_data_source_config() -> dict[str, Any]:
    """evals.create の data_source_config(custom スキーマ)。"""
    return {
        "type": "custom",
        "item_schema": ITEM_SCHEMA,
        "include_sample_schema": False,  # 完成品の採点のみ(モデル再実行なし)
    }


def build_testing_criteria(model: str, include_rubric: bool = True) -> list[dict[str, Any]]:
    """組み込み評価器 2 つ(builtin.coherence / builtin.fluency)+ rubric
    (score_model)の testing_criteria を組み立てる。

    - coherence は query+response、fluency は response のみを見る
      (data_mapping で item のフィールドへ写像)
    - rubric は openai ネイティブの score_model グレーダー。判定モデルは
      プロジェクトのデプロイ名(= 実行時 critic と同じモデルにできる)
    """
    criteria: list[dict[str, Any]] = [
        {
            "type": "azure_ai_evaluator",
            "name": "coherence",
            "evaluator_name": "builtin.coherence",
            "initialization_parameters": {"deployment_name": model},
            "data_mapping": {"query": "{{item.prompt}}", "response": "{{item.answer}}"},
        },
        {
            "type": "azure_ai_evaluator",
            "name": "fluency",
            "evaluator_name": "builtin.fluency",
            "initialization_parameters": {"deployment_name": model},
            "data_mapping": {"response": "{{item.answer}}"},
        },
    ]
    if include_rubric:
        criteria.append(
            {
                "type": "score_model",
                "name": "revision_rubric",
                "model": model,
                "range": [1, 5],
                "input": [
                    {"role": "system", "content": RUBRIC_SYSTEM_PROMPT},
                    {"role": "user", "content": RUBRIC_USER_TEMPLATE},
                ],
            }
        )
    return criteria


def build_data_source(items: list[dict[str, Any]]) -> dict[str, Any]:
    """evals.runs.create の data_source(インライン JSONL)。"""
    return {
        "type": "jsonl",
        "source": {"type": "file_content", "content": [{"item": item} for item in items]},
    }


def summarize_output_items(output_items: list[dict[str, Any]]) -> dict[str, Any]:
    """評価ランの output items(dict 化済み)を stage × grader で集計する。

    入力の各要素は ``{"datasource_item": {...}, "results": [{"name", "score",
    "passed"}, ...]}`` の形(openai SDK の OutputItemListResponse.model_dump()
    互換)。戻り値は stage_index 順の per-stage 平均スコア表。
    """
    scores: dict[tuple[int, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    verdicts: dict[tuple[int, str], str] = {}
    graders: list[str] = []

    for output_item in output_items:
        item = output_item.get("datasource_item", {})
        key = (int(item.get("stage_index", 0)), str(item.get("stage", "?")))
        verdicts[key] = str(item.get("runtime_verdict", ""))
        for result in output_item.get("results", []):
            name = str(result.get("name", "?"))
            if name not in graders:
                graders.append(name)
            score = result.get("score")
            if score is not None:
                scores[key][name].append(float(score))

    stages = []
    for key in sorted(scores):
        stage_index, stage = key
        stages.append(
            {
                "stage": stage,
                "stage_index": stage_index,
                "runtime_verdict": verdicts.get(key, ""),
                "scores": {
                    name: sum(values) / len(values)
                    for name, values in scores[key].items()
                    if values
                },
                "count": max((len(v) for v in scores[key].values()), default=0),
            }
        )
    return {"graders": graders, "stages": stages}


def format_summary(summary: dict[str, Any]) -> str:
    """集計を「実行時 verdict と並べた」テキスト表にする。

    クラウド評価のスコアが initial → 最終版で上がっていれば、実行時の
    自己批評(revise 判定 → 改訂)が実際に品質を押し上げたことの傍証になる。
    """
    graders = summary["graders"]
    header = ["stage", "runtime_verdict", *graders]
    rows = [header]
    for stage in summary["stages"]:
        rows.append(
            [
                stage["stage"],
                stage["runtime_verdict"],
                *[
                    f"{stage['scores'][name]:.2f}" if name in stage["scores"] else "-"
                    for name in graders
                ],
            ]
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    lines = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in rows]

    # initial → 最終 stage のスコア差(傾向の一致検証の一次指標)
    stages = summary["stages"]
    if len(stages) >= 2:
        first, last = stages[0], stages[-1]
        deltas = [
            f"{name}: {last['scores'][name] - first['scores'][name]:+.2f}"
            for name in graders
            if name in first["scores"] and name in last["scores"]
        ]
        if deltas:
            lines.append(f"delta {first['stage']} -> {last['stage']}: " + ", ".join(deltas))
    return "\n".join(lines)
