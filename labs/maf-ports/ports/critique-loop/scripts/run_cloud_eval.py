"""Foundry クラウド評価の実行(ライブ専用・データプレーン)。

ループの各周回の中間出力(初稿 / 改訂1 / 改訂2)を Foundry の evals API で
採点し、実行時の自己批評(critic の verdict)とスコア傾向を突き合わせる:

    # 1. ループを実行して版ごとの中間出力を保存
    uv run critique-loop-maf "Explain recursion with examples." --save-run runs/recursion.json

    # 2. クラウド評価(要 az login + FOUNDRY_PROJECT_ENDPOINT。--dry-run は送信内容の確認のみ)
    uv sync --extra eval
    uv run python scripts/run_cloud_eval.py runs/*.json
    uv run python scripts/run_cloud_eval.py runs/*.json --dry-run
    uv run python scripts/run_cloud_eval.py runs/*.json --no-rubric

経路(azure-ai-projects 2.4 精読の結論 — README「evals API 調査」参照):
``AIProjectClient(project_endpoint, DefaultAzureCredential()).get_openai_client()``
が返す openai SDK クライアントの ``.evals`` を使う。組み込み評価器
(builtin.coherence / builtin.fluency)は Azure 拡張の testing_criteria
``{"type": "azure_ai_evaluator", ...}``、rubric は openai ネイティブの
``score_model`` グレーダー。評価器の実行はサーバー側(判定モデルの
トークン課金がプロジェクト側に発生する)。

Bicep との関係: 評価グループ/ランはデータプレーンのオブジェクトで ARM では
作れない(travel-memory の Memory ストアと同じ「2 段デプロイ」の 2 段目)。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PORT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT_ROOT / "src"))

from critique_loop_maf.cloud_eval import (
    build_data_source,
    build_data_source_config,
    build_eval_items,
    build_testing_criteria,
    format_summary,
    summarize_output_items,
)
from critique_loop_maf.config import ConfigError, FoundrySettings

TERMINAL_STATUSES = {"completed", "failed", "canceled", "cancelled"}


def main() -> None:
    parser = argparse.ArgumentParser(description="critique-loop のクラウド評価(evals API)")
    parser.add_argument(
        "runs", nargs="+", help="critique-loop-maf --save-run が書いた実行結果 JSON"
    )
    parser.add_argument("--name", default="critique-loop-stages", help="評価グループ名")
    parser.add_argument(
        "--no-rubric", action="store_true", help="rubric(score_model)評価器を除外"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="送信せず評価アイテムと評価器定義を表示(ネットワーク不要)",
    )
    parser.add_argument("--poll-interval", type=float, default=10.0, help="ポーリング間隔秒")
    parser.add_argument("--timeout", type=float, default=900.0, help="ラン完了待ちの上限秒")
    args = parser.parse_args()

    items = []
    for run_path in args.runs:
        run = json.loads(Path(run_path).read_text(encoding="utf-8"))
        items.extend(build_eval_items(run, run_label=Path(run_path).stem))
    if not items:
        print("error: 評価アイテムが 0 件", file=sys.stderr)
        sys.exit(2)

    try:
        settings = FoundrySettings.from_env()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    criteria = build_testing_criteria(settings.model, include_rubric=not args.no_rubric)

    if args.dry_run:
        print(json.dumps({"testing_criteria": criteria, "items": items}, ensure_ascii=False,
                         indent=2))
        return

    if not settings.project_endpoint:
        print(
            "error: FOUNDRY_PROJECT_ENDPOINT が未設定(クラウド評価は"
            "プロジェクトエンドポイント+Entra ID が必要。labs/maf-ports/.env を確認)",
            file=sys.stderr,
        )
        sys.exit(2)

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    project = AIProjectClient(
        endpoint=settings.project_endpoint, credential=DefaultAzureCredential()
    )
    client = project.get_openai_client()

    eval_group = client.evals.create(
        name=args.name,
        data_source_config=build_data_source_config(),
        testing_criteria=criteria,  # type: ignore[arg-type]  # Azure 拡張 dict を含む
    )
    print(f"eval group: {eval_group.id}", file=sys.stderr)

    run = client.evals.runs.create(
        eval_id=eval_group.id,
        name=f"{args.name}-run",
        data_source=build_data_source(items),  # type: ignore[arg-type]
    )
    print(f"eval run: {run.id} (status={run.status})", file=sys.stderr)

    deadline = time.monotonic() + args.timeout
    while run.status not in TERMINAL_STATUSES:
        if time.monotonic() > deadline:
            print(f"error: timeout ({args.timeout:.0f}s) — 最終 status={run.status}",
                  file=sys.stderr)
            sys.exit(1)
        time.sleep(args.poll_interval)
        run = client.evals.runs.retrieve(run.id, eval_id=eval_group.id)
        print(f"  status={run.status}", file=sys.stderr)

    report_url = getattr(run, "report_url", "")
    if report_url:
        print(f"report: {report_url}", file=sys.stderr)
    if run.status != "completed":
        print(f"error: eval run {run.status}", file=sys.stderr)
        sys.exit(1)

    output_items = [
        item.model_dump()
        for item in client.evals.runs.output_items.list(run.id, eval_id=eval_group.id)
    ]
    print(format_summary(summarize_output_items(output_items)))


if __name__ == "__main__":
    main()
