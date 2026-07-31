"""code_interpreter ツール定義の組み立てのオフラインテスト。実接続はしない。

境界は「ファクトリ関数」: 記録フェイクの注入(factory=)と、実
``OpenAIChatClient.get_code_interpreter_tool``(静的メソッド・ネットワーク
不要)が返す dict の形の両方を固定する。この dict がそのまま Responses API の
tools 配列に載る(パススルーは agent_framework_openai _chat_client.py 983 行)。"""

from typing import Any

import pytest

from data_analysis_ci_maf.tools import (
    CodeInterpreterUnsupportedError,
    build_code_interpreter_tool,
)

# --- ファクトリ注入(記録フェイク)---


def test_factory_injection_receives_file_ids() -> None:
    calls: list[dict[str, Any]] = []

    def fake_factory(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"type": "code_interpreter"}

    tool = build_code_interpreter_tool(object(), ["file-abc123"], factory=fake_factory)

    assert tool == {"type": "code_interpreter"}
    assert calls == [{"file_ids": ["file-abc123"]}]


# --- 実クライアントのファクトリ(SupportsCodeInterpreterTool プロトコル)---


def test_real_openai_chat_client_supports_code_interpreter() -> None:
    """HostedCodeInterpreterTool クラスは現行 MAF に存在しない。現行 API は
    クライアント静的ファクトリ + プロトコル(README の調査結果)。"""
    pytest.importorskip("agent_framework")
    from agent_framework import SupportsCodeInterpreterTool
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(
        model="gpt-5.4-mini",
        api_key="dummy",
        base_url="https://example.openai.azure.com/openai/v1",
    )
    assert isinstance(client, SupportsCodeInterpreterTool)


def test_real_factory_builds_container_tool_dict() -> None:
    pytest.importorskip("agent_framework")
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(
        model="gpt-5.4-mini",
        api_key="dummy",
        base_url="https://example.openai.azure.com/openai/v1",
    )

    tool = build_code_interpreter_tool(client, ["file-abc123", "file-def456"])

    # openai SDK の CodeInterpreter TypedDict = 素の dict(Responses API 形式)
    assert isinstance(tool, dict)
    assert tool["type"] == "code_interpreter"
    assert tool["container"] == {"type": "auto", "file_ids": ["file-abc123", "file-def456"]}


def test_unsupported_client_raises_with_responses_api_hint() -> None:
    """ファクトリを持たないクライアントでは「openai クライアント直へ切り替え」を
    案内する(README『Responses API 直との使い分け』の分岐をコードに固定)。"""

    class NoToolsClient:
        pass

    with pytest.raises(CodeInterpreterUnsupportedError) as excinfo:
        build_code_interpreter_tool(NoToolsClient(), ["file-abc123"])

    message = str(excinfo.value)
    assert "NoToolsClient" in message
    assert "openai クライアント直" in message
