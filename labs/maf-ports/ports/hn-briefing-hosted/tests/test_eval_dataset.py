"""評価データセット(eval_dataset.jsonl)とランキング実装の整合をオフラインで固定。

PORTING.md §3: オフラインは期待挙動のアサーション。決定論部分(キーワード/
ノイズ/順位)はデータ駆動でここで検証し、LLM 部分(brief_md の品質)は
ライブでクラウド評価に渡す(README の評価節)。
"""

import json
from pathlib import Path

import pytest

from hn_briefing_maf.hn import Story
from hn_briefing_maf.ranking import is_noise, keyword_hits, score_story

DATASET_PATH = Path(__file__).parent / "eval_dataset.jsonl"


def load_dataset() -> list[dict]:
    return [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def make_story(fields: dict) -> Story:
    return Story(
        title=fields["title"],
        url="https://example.com/x",
        hn_url="https://news.ycombinator.com/item?id=1",
        points=fields["points"],
        comments=fields["comments"],
        rank=fields["rank"],
    )


def test_dataset_covers_all_kinds() -> None:
    kinds = {case["kind"] for case in load_dataset()}
    assert kinds == {"keyword", "noise", "rank_order"}
    assert len(load_dataset()) >= 5


@pytest.mark.parametrize(
    "case",
    [case for case in load_dataset() if case["kind"] == "keyword"],
    ids=lambda case: case["id"],
)
def test_keyword_cases(case: dict) -> None:
    assert keyword_hits(case["title"]) == set(case["expected_hits"])


@pytest.mark.parametrize(
    "case",
    [case for case in load_dataset() if case["kind"] == "noise"],
    ids=lambda case: case["id"],
)
def test_noise_cases(case: dict) -> None:
    assert is_noise(case["title"]) is case["expected_noise"]


@pytest.mark.parametrize(
    "case",
    [case for case in load_dataset() if case["kind"] == "rank_order"],
    ids=lambda case: case["id"],
)
def test_rank_order_cases(case: dict) -> None:
    higher = score_story(make_story(case["higher"]))
    lower = score_story(make_story(case["lower"]))
    assert higher > lower, case["note"]
