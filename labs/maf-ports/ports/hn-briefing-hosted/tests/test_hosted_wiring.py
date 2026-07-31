"""hosted agent エントリポイントの配線検証(実デプロイなし)。

3 層で固定する:

1. 関数ツール collect_ranked_stories の実挙動(MockTransport — コンテナ内
   httpx 呼び出しの決定論部分)
2. 実 MAF ``Agent`` の組み立て(instructions / tools / store=False)
3. hosting/main.py の実 import + ResponsesHostServer の構築(run() はしない。
   agent-framework-foundry-hosting が必要 → uv sync --extra dev --extra hosting)
"""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("agent_framework")

from conftest import EXTRA_HITS, SAMPLE_HITS, algolia_client, algolia_payload

from hn_briefing_maf.agents import build_chat_client
from hn_briefing_maf.config import FoundrySettings
from hn_briefing_maf.hosted import (
    HOSTED_INSTRUCTIONS,
    build_hosted_briefing_agent,
    make_collect_tool,
)

PORT_ROOT = Path(__file__).resolve().parents[1]
HOSTING_MAIN = PORT_ROOT / "hosting" / "main.py"


def make_settings() -> FoundrySettings:
    return FoundrySettings(
        openai_v1_endpoint="https://fake.openai.azure.com/openai/v1",
        model="gpt-fake",
        api_key="fake-key",
        app_insights_connection_string=None,
    )


# --- 1. 関数ツール(エージェント内部の httpx 呼び出し)---


async def test_collect_tool_returns_ranked_digest() -> None:
    http, _ = algolia_client(algolia_payload([*SAMPLE_HITS, *EXTRA_HITS]))
    try:
        tool = make_collect_tool(http)
        digest = await tool(top_n=3)
    finally:
        await http.aclose()

    assert "1. Show HN: An open-source framework" in digest
    assert "front-page rank" in digest
    assert "who is hiring" not in digest.lower()  # ノイズ除去まで含めてツール内で完結
    assert "4." not in digest  # top_n=3


async def test_collect_tool_clamps_top_n() -> None:
    http, _ = algolia_client()
    try:
        digest = await make_collect_tool(http)(top_n=999)  # クランプ → 10
    finally:
        await http.aclose()
    assert "5. " in digest  # サンプルは 5 篇


# --- 2. 実 Agent の組み立て ---


def build_agent():
    return build_hosted_briefing_agent(build_chat_client(make_settings()), object())


def test_agent_wires_instructions_and_collect_tool() -> None:
    agent = build_agent()

    assert agent.default_options.get("instructions") == HOSTED_INSTRUCTIONS
    tools = agent.default_options.get("tools") or []
    names = [getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools]
    assert names == ["collect_ranked_stories"]
    # 会話履歴はホスティング基盤(conversation ID)管理 → モデル側 store は切る
    assert agent.default_options.get("store") is False


def test_hosted_instructions_port_original_operating_rules() -> None:
    """元 agent.py の運用規約の残滓: ツール呼び出し規約 / observation と
    delivery の分離 / 簡潔・運用的、の 3 点が instructions に現れること。"""
    assert "collect_ranked_stories" in HOSTED_INSTRUCTIONS
    assert "do not claim to send messages or" in HOSTED_INSTRUCTIONS
    assert "concise and operational" in HOSTED_INSTRUCTIONS
    assert "never reorder" in HOSTED_INSTRUCTIONS  # ランキングは決定論段の責務


# --- 3. hosting/main.py の実配線 ---


def test_hosting_entrypoint_files_exist_with_container_contract() -> None:
    """zip ルート規約のファイルが hosting/ に揃い、main.py が Responses
    protocol サーバーと agent identity(キーレス)経路を使うこと。"""
    assert HOSTING_MAIN.is_file()
    source = HOSTING_MAIN.read_text(encoding="utf-8")
    assert "ResponsesHostServer" in source
    assert "DefaultAzureCredential" in source
    assert "FoundryChatClient" in source
    assert "FOUNDRY_API_KEY" not in source  # hosted 実行にキーを持ち込まない

    requirements = (PORT_ROOT / "hosting" / "requirements.txt").read_text(encoding="utf-8")
    for package in (
        "agent-framework-core",
        "agent-framework-foundry",
        "agent-framework-foundry-hosting",
        "azure-identity",
        "httpx",
    ):
        assert package in requirements, f"hosting/requirements.txt に {package} が無い"


def test_hosting_main_imports_and_builds_server_without_running() -> None:
    """main.py を実 import し、ResponsesHostServer(agent) の構築まで検証する
    (run() はしない)。ホスティング層の依存が無い環境では skip。"""
    pytest.importorskip("agent_framework_foundry_hosting")

    spec = importlib.util.spec_from_file_location("hosting_main", HOSTING_MAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # main() は呼ばない(env 不要)
    assert callable(module.main)

    from agent_framework_foundry_hosting import ResponsesHostServer

    # configure_observability=None: 既定ではコンストラクタが OTel 距離(distro)を
    # 構成し、Azure リソース検出が IMDS(169.254.169.254)を突く。オフライン
    # テストでは切る(コンテナ実機では既定のまま = App Insights 自動配線)。
    server = ResponsesHostServer(build_agent(), configure_observability=None)
    assert server is not None
