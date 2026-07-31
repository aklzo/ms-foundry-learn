"""クラウド評価(cloud_eval.py)の純ロジックのオフラインテスト。

scripts/run_cloud_eval.py が evals API に送る内容(評価アイテム・評価器定義・
データソース)と、結果集計を、ネットワークなしで固定する。
"""

import json
from pathlib import Path

from critique_loop_maf.cloud_eval import (
    ITEM_SCHEMA,
    RUNTIME_ACCEPT,
    RUNTIME_REVISE,
    RUNTIME_UNEVALUATED,
    build_data_source,
    build_data_source_config,
    build_eval_items,
    build_testing_criteria,
    format_summary,
    summarize_output_items,
)

#: CLI --save-run 出力(CritiqueLoopResult.to_dict())の形
EXHAUSTED_RUN = {
    "prompt": "Explain recursion.",
    "initial_answer": "draft-0",
    "final_answer": "draft-2",
    "candidates": [],
    "revisions": [
        {"round": 1, "critiques": ["add examples"], "answer": "draft-1"},
        {"round": 2, "critiques": ["explain base case"], "answer": "draft-2"},
    ],
    "stop_reason": "max-rounds",
    "max_rounds": 2,
    "total_iterations": 3,
}

ACCEPTED_RUN = {
    "prompt": "What is an API?",
    "initial_answer": "draft-0",
    "final_answer": "draft-1",
    "candidates": [],
    "revisions": [{"round": 1, "critiques": ["be specific"], "answer": "draft-1"}],
    "stop_reason": "accepted",
    "max_rounds": 2,
    "total_iterations": 2,
}


# --- 評価アイテムの組み立て -------------------------------------------------


def test_eval_items_cover_every_stage_in_order() -> None:
    items = build_eval_items(EXHAUSTED_RUN, run_label="recursion")

    assert [(i["stage"], i["stage_index"]) for i in items] == [
        ("initial", 0),
        ("revision-1", 1),
        ("revision-2", 2),
    ]
    assert [i["answer"] for i in items] == ["draft-0", "draft-1", "draft-2"]
    assert all(i["prompt"] == "Explain recursion." for i in items)
    assert all(i["run_label"] == "recursion" for i in items)


def test_runtime_verdict_mapping_for_max_rounds_run() -> None:
    """上限打ち切りの実行では、最終改訂は実行時に批評されていない
    (unevaluated)— クラウド評価がそこを補完する、という役割分担の根拠。"""
    items = build_eval_items(EXHAUSTED_RUN)

    assert [i["runtime_verdict"] for i in items] == [
        RUNTIME_REVISE,
        RUNTIME_REVISE,
        RUNTIME_UNEVALUATED,
    ]


def test_runtime_verdict_mapping_for_accepted_run() -> None:
    items = build_eval_items(ACCEPTED_RUN)

    assert [i["runtime_verdict"] for i in items] == [RUNTIME_REVISE, RUNTIME_ACCEPT]


def test_eval_items_for_no_revision_run() -> None:
    run = {**ACCEPTED_RUN, "revisions": [], "final_answer": "draft-0"}
    items = build_eval_items(run)

    assert len(items) == 1
    assert items[0]["stage"] == "initial"
    assert items[0]["runtime_verdict"] == RUNTIME_ACCEPT


def test_items_conform_to_item_schema_required_fields() -> None:
    for item in build_eval_items(EXHAUSTED_RUN):
        for required in ITEM_SCHEMA["required"]:
            assert item.get(required), f"required field missing: {required}"


# --- 評価器定義とデータソース ----------------------------------------------


def test_testing_criteria_builtin_pair_and_rubric() -> None:
    criteria = build_testing_criteria("gpt-5.4-mini")

    assert [c["type"] for c in criteria] == ["azure_ai_evaluator", "azure_ai_evaluator",
                                             "score_model"]
    coherence, fluency, rubric = criteria
    assert coherence["evaluator_name"] == "builtin.coherence"
    assert coherence["data_mapping"] == {
        "query": "{{item.prompt}}",
        "response": "{{item.answer}}",
    }
    assert fluency["evaluator_name"] == "builtin.fluency"
    assert fluency["data_mapping"] == {"response": "{{item.answer}}"}
    # rubric はプロジェクトのデプロイ名を判定モデルに使う(実行時 critic と同じにできる)
    assert rubric["model"] == "gpt-5.4-mini"
    assert rubric["range"] == [1, 5]
    assert "{{item.answer}}" in rubric["input"][1]["content"]


def test_testing_criteria_without_rubric() -> None:
    criteria = build_testing_criteria("gpt-5.4-mini", include_rubric=False)
    assert [c["name"] for c in criteria] == ["coherence", "fluency"]


def test_data_source_config_is_custom_schema_without_sample() -> None:
    config = build_data_source_config()
    assert config["type"] == "custom"
    assert config["item_schema"] == ITEM_SCHEMA
    assert config["include_sample_schema"] is False  # 完成品採点(モデル再実行なし)


def test_data_source_wraps_items_as_inline_jsonl() -> None:
    items = build_eval_items(ACCEPTED_RUN)
    source = build_data_source(items)

    assert source["type"] == "jsonl"
    assert source["source"]["type"] == "file_content"
    assert [row["item"] for row in source["source"]["content"]] == items
    # openai SDK にそのまま渡せる(JSON 直列化可能)
    json.dumps(source)


# --- 結果集計 ---------------------------------------------------------------


def make_output_item(stage: str, index: int, verdict: str, scores: dict[str, float]) -> dict:
    return {
        "datasource_item": {
            "prompt": "p",
            "stage": stage,
            "stage_index": index,
            "runtime_verdict": verdict,
        },
        "results": [
            {"name": name, "score": score, "passed": score >= 3} for name, score in scores.items()
        ],
    }


def test_summarize_orders_stages_and_averages_scores() -> None:
    output_items = [
        # 2 run 分の同一 stage が平均される。順序はシャッフルして入れる
        make_output_item("revision-1", 1, "unevaluated", {"coherence": 4.0, "fluency": 5.0}),
        make_output_item("initial", 0, "revise", {"coherence": 2.0, "fluency": 3.0}),
        make_output_item("initial", 0, "revise", {"coherence": 4.0, "fluency": 3.0}),
    ]
    summary = summarize_output_items(output_items)

    assert [s["stage"] for s in summary["stages"]] == ["initial", "revision-1"]
    initial, revision = summary["stages"]
    assert initial["scores"]["coherence"] == 3.0  # (2+4)/2
    assert initial["count"] == 2
    assert initial["runtime_verdict"] == "revise"
    assert revision["scores"]["fluency"] == 5.0
    assert revision["runtime_verdict"] == "unevaluated"


def test_format_summary_shows_verdicts_and_delta() -> None:
    summary = summarize_output_items(
        [
            make_output_item("initial", 0, "revise", {"coherence": 3.0}),
            make_output_item("revision-1", 1, "accept", {"coherence": 4.5}),
        ]
    )
    text = format_summary(summary)

    assert "runtime_verdict" in text
    assert "revise" in text and "accept" in text
    # initial → 最終版のスコア差(傾向一致検証の一次指標)
    assert "delta initial -> revision-1" in text
    assert "coherence: +1.50" in text


def test_summarize_tolerates_missing_scores() -> None:
    items = [
        {
            "datasource_item": {"stage": "initial", "stage_index": 0},
            "results": [{"name": "coherence", "score": None, "passed": False}],
        }
    ]
    summary = summarize_output_items(items)
    assert summary["stages"] == []  # スコアなしの stage は集計に出さない


def test_run_cloud_eval_script_exists_and_mentions_dry_run() -> None:
    """スクリプトの存在と入口の体裁(実行はライブ側の手順)。"""
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_cloud_eval.py"
    text = script.read_text(encoding="utf-8")
    assert "get_openai_client" in text
    assert "--dry-run" in text
