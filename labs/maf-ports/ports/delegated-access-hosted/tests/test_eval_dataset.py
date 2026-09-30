"""評価データセット(eval_dataset.jsonl)の権限の期待値を、オフラインの全部品結合で確かめる。

モデルは台本(期待ツールが見えていれば呼び、見えていなければ呼ばずに答える)なので、ここで
固定できるのは「利用者ごとに見えるツール」「実行・拒否・絞り込みの結果」まで。モデルが質問から
正しいツールを選ぶかはライブ評価の対象(runbook §6)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("azure.ai.agentserver.responses")

from delegated_access_maf.contracts import BASELINE_DOC_ROLE
from delegated_access_maf.devtools.fake_entra import USERS, FakeEntra
from delegated_access_maf.tools_server.docs_search import InMemoryDocs
from delegated_access_maf.tools_server.offline import offline_tools_server
from delegated_access_maf.tools_server.settings import DEFAULT_DOCS_DIR
from tests.caller_fakes import (
    ModelCall,
    ScriptedChatClient,
    last_tool_result,
    text_reply,
    tool_call_reply,
)
from tests.test_e2e_offline import MODES, Stack

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

CASES = [
    json.loads(line)
    for line in (Path(__file__).parent / "eval_dataset.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
    if line.strip()
]
FINANCE_ONLY = {
    doc.id
    for doc in InMemoryDocs.from_dir(DEFAULT_DOCS_DIR).documents
    if BASELINE_DOC_ROLE not in doc.allowed_roles
}


def script_for(case: dict):
    def script(index: int, call: ModelCall):
        if index == 0 and case["expected_tool"] in call.tool_names:
            return tool_call_reply((case["expected_tool"], case["tool_args"]))
        if index == 0:
            return text_reply("NO_TOOL")
        return text_reply(last_tool_result(call))

    return script


def test_dataset_is_well_formed() -> None:
    assert 5 <= len(CASES) <= 10
    assert len({c["id"] for c in CASES}) == len(CASES)
    for case in CASES:
        assert case["user"] in USERS
        assert case["expected_outcome"] in {
            "answered",
            "not_permitted",
            "updated",
            "rejected_by_rule",
            "trimmed",
            "finance_docs_visible",
        }


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_case_access_expectation(case: dict, mode: str) -> None:
    entra = FakeEntra()
    async with offline_tools_server(entra, enforcement=mode) as tools:
        stack = Stack(entra, tools, ScriptedChatClient(script_for(case)))
        before = {s.supplier_id: s.payment_terms_days for s in tools.suppliers.all_suppliers()}
        try:
            response = await stack.ask(case["user"], case["question"])
        finally:
            await stack.aclose()

        body = response.json()
        assert response.status_code == 200, body
        assert body["visible_servers"] == case["expected_visible_servers"]
        answer = body["answer"]
        after = {s.supplier_id: s.payment_terms_days for s in tools.suppliers.all_suppliers()}
        outcome = case["expected_outcome"]

        if outcome == "updated":
            args = case["tool_args"]
            assert after[args["supplier_id"]] == args["days"]
            [record] = tools.suppliers.audit_log
            assert record.oid == USERS[case["user"]].oid
        else:
            assert after == before  # 更新以外のケースでは基幹データが変わらない
            assert tools.suppliers.audit_log == []

        if outcome == "not_permitted":
            assert answer == "NO_TOOL"  # モデルには更新ツールが渡っていない
        if outcome == "rejected_by_rule":
            assert "60 日以内" in answer
        if outcome in {"trimmed", "finance_docs_visible"}:
            ids = {hit["id"] for hit in json.loads(answer)["results"]}
            if outcome == "trimmed":
                assert not (ids & FINANCE_ONLY)
            else:
                assert ids & FINANCE_ONLY
        if outcome == "answered":
            assert answer and answer != "NO_TOOL"
