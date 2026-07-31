"""eval_dataset.jsonl(5 ケース)の整合性検証。

本ポートの評価対象は「どの役割間通信が発生すべきか」。オフラインでは
(1) 期待通信(must_comms)がグラフ上**達成可能**であること、
(2) forbidden_comms がグラフで**構造的に不可能**(ツール不在)であること、
(3) プロジェクト入力が元フォームの選択肢に収まること、を固定する。
ライブでは実行後の ``agency.log.agent_pairs()`` と must_comms を突き合わせる
(README の評価節。PORTING §3 に従い合否ラインは設けない)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services_agency_maf.agency import Agency
from services_agency_maf.flows import AGENT_KEYS, COMMUNICATION_FLOWS, talk_tool_name
from services_agency_maf.project import (
    BUDGET_RANGES,
    PRIORITIES,
    PROJECT_TYPES,
    TIMELINES,
    ProjectInfo,
)
from services_agency_maf.roles import entry_prompt

DATASET = Path(__file__).parent / "eval_dataset.jsonl"


def load_cases() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line]


CASES = load_cases()
CASE_IDS = [case["id"] for case in CASES]


def to_project(case: dict) -> ProjectInfo:
    project = case["project"]
    return ProjectInfo(
        name=project["name"],
        description=project["description"],
        project_type=project["type"],
        timeline=project["timeline"],
        budget=project["budget"],
        priority=project["priority"],
        technical_requirements=project.get("technical_requirements", ""),
        special_considerations=project.get("special_considerations", ""),
    )


def test_dataset_has_enough_unique_cases() -> None:
    assert len(CASES) >= 5
    assert len(set(CASE_IDS)) == len(CASES)


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_project_fields_match_original_form_choices(case: dict) -> None:
    project = case["project"]
    assert project["type"] in PROJECT_TYPES
    assert project["budget"] in BUDGET_RANGES
    assert project["timeline"] in TIMELINES
    assert project["priority"] in PRIORITIES
    assert project["name"] and project["description"]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_must_comms_are_achievable_on_graph(case: dict) -> None:
    """期待通信は許可グラフの部分集合(達成可能性)。"""
    must = [tuple(pair) for pair in case["expect"]["must_comms"]]
    assert must, case["id"]
    assert set(must) <= set(COMMUNICATION_FLOWS), case["id"]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_forbidden_comms_are_structurally_impossible(case: dict) -> None:
    """forbidden はグラフ外であり、実際に送信側へツールが生成されない。"""
    agency = Agency()
    for sender, recipient in (tuple(pair) for pair in case["expect"]["forbidden_comms"]):
        assert sender in AGENT_KEYS and recipient in AGENT_KEYS, case["id"]
        assert (sender, recipient) not in set(COMMUNICATION_FLOWS), case["id"]
        names = {tool.__name__ for tool in agency.talk_tools(sender)}
        assert talk_tool_name(recipient) not in names, case["id"]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_entry_prompts_build_for_each_case(case: dict) -> None:
    project = to_project(case)
    for key in AGENT_KEYS:
        prompt = entry_prompt(key, project)
        assert prompt.strip()
    assert project.name in entry_prompt("ceo", project)
