"""実 MAF ``Agent`` + 実ツール dict の配線オフラインテスト(ネットワーク不要)。

MCP ツール(github-mcp ポート)とは対照的に、code_interpreter の dict は
**通常ツール**として ``agent.default_options["tools"]`` に載る(dict は
normalize_tools をそのまま通過 — agent_framework _tools.py 990 行)。
クライアント側に接続ライフサイクルは無い(サーバー側ツール)。"""

import pytest

pytest.importorskip("agent_framework")

from data_analysis_ci_maf.agents import INSTRUCTIONS, build_analyst_agent, build_chat_client
from data_analysis_ci_maf.config import FoundrySettings
from data_analysis_ci_maf.tools import build_code_interpreter_tool

SETTINGS = FoundrySettings(
    openai_v1_endpoint="https://example.openai.azure.com/openai/v1",
    model="gpt-5.4-mini",
    api_key="dummy",
    app_insights_connection_string=None,
)


def test_agent_holds_code_interpreter_as_plain_tool() -> None:
    chat_client = build_chat_client(SETTINGS)
    tool = build_code_interpreter_tool(chat_client, ["file-abc123"])

    agent = build_analyst_agent(chat_client, tool)

    # dict ツールは default_options["tools"] へ(mcp_tools ではない)
    assert agent.default_options.get("tools") == [tool]
    assert agent.mcp_tools == []
    assert callable(agent.run)


def test_agent_instructions_keep_original_skeleton() -> None:
    """元 system_message の骨格(expert data analyst / 対象データ / 手段 /
    簡潔な回答)を保ち、手段だけ DuckDB SQL → Code Interpreter の Python。"""
    chat_client = build_chat_client(SETTINGS)
    tool = build_code_interpreter_tool(chat_client, ["file-abc123"])

    agent = build_analyst_agent(chat_client, tool)

    instructions = agent.default_options.get("instructions")
    assert instructions == INSTRUCTIONS
    assert instructions.startswith("You are an expert data analyst.")
    assert "code interpreter" in instructions
    assert "DuckDB" not in instructions  # 手段の置き換えが完了している


def test_chat_client_targets_foundry_v1_endpoint() -> None:
    chat_client = build_chat_client(SETTINGS)

    assert chat_client.model == "gpt-5.4-mini"
    # アップロードに再利用する内包 AsyncOpenAI(cli.py の chat_client.client.files)
    assert hasattr(chat_client.client, "files")
