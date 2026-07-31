"""1 クエリの実行と、応答からのルーティング観測の抽出。

元アプリはルーティングの経過を Streamlit に逐次表示していた
(st.success("Using vector similarity routing: ...") 等)。移植後は
ルーティングがサービス側+エージェントのツール選択に移ったため、
「どのツールが呼ばれたか」(knowledge_base_retrieve か web_search か)が
それに相当する観測点になる。:func:`summarize_tool_calls` が応答メッセージ
から抽出し、CLI が stderr に表示・ライブスモークが検証に使う。
"""

from __future__ import annotations

import asyncio
from typing import Any

from .agents import SupportsRun

#: 元アプリに全体タイムアウトは無い(Streamlit の spinner 任せ)。CLI /
#: スモークの運用上の安全弁として追加した移植差分(README の元との差分参照)。
DEFAULT_TIMEOUT_SECONDS = 180.0


async def run_query(
    agent: SupportsRun,
    question: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """エージェントを 1 回実行して応答オブジェクトを返す(タイムアウト付き)。

    応答テキストは ``.text``、ツール呼び出しは :func:`summarize_tool_calls` で
    取り出す。タイムアウト時は TimeoutError が送出される。
    """
    return await asyncio.wait_for(agent.run(question), timeout)


def response_text(response: Any) -> str:
    """応答テキスト(空応答は例外にしない — 元アプリはそのまま表示する)。"""
    return getattr(response, "text", "") or ""


def summarize_tool_calls(response: Any) -> list[str]:
    """応答メッセージからツール呼び出し名を出現順(重複除去)で抽出する。

    MAF の AgentRunResponse は ``.messages[].contents[]`` に
    FunctionCallContent(``name`` と ``call_id`` を持つ)を含む。fake でも
    動くよう duck-typing で拾う。
    """
    seen: list[str] = []
    for message in getattr(response, "messages", []) or []:
        for content in getattr(message, "contents", []) or []:
            name = getattr(content, "name", None)
            call_id = getattr(content, "call_id", None)
            if name and call_id is not None and name not in seen:
                seen.append(name)
    return seen
