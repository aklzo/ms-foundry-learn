"""Agency = エージェント登録簿+通信グラフ+共有状態+通信ログ。

Port 13 の核心「動的な会話開始 × グラフ制約」の MAF 表現:

(a) LLM が**実行時に**通信相手を選ぶ — 各エージェントに talk_to_* 関数ツール
    を持たせ、呼ぶかどうか・誰を呼ぶか・何を聞くかをモデルの裁量にする。
(b) 選択肢は communication_flows の**有向グラフで制約** — ツールは
    :func:`flows.allowed_recipients` にあるペアからしか**生成しない**。
    非許可ペアは「ツールが存在しない」ため、モデルがどう頑張っても通信
    できない(プロンプト制約でなく構造制約)。
(c) 会話は agent-as-tool の**再帰呼び出し** — talk ツールの実装が相手
    Agent.run を await し、応答文字列をツール結果として返す。送信側 LLM は
    それを自分の応答に統合する。相手にも talk ツールがあるため会話は入れ子に
    なる(深度は comms.py の ContextVar で打ち切り)。

グラフ Workflow(WorkflowBuilder)を使わない判断: Workflow のエッジは
「メッセージが流れる固定経路」で、実行時に LLM が行き先を選ぶ+**応答が
呼び出し元に戻る**(呼び出し規約が関数呼び出し)という Agency Swarm の
意味論はエッジでは表現できない(README 学び 1)。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .comms import DEFAULT_MAX_DEPTH, CommListener, CommLog, at_depth, current_depth
from .config import FoundrySettings
from .flows import (
    AGENT_KEYS,
    COMMUNICATION_FLOWS,
    DESCRIPTIONS,
    DISPLAY_NAMES,
    Flows,
    allowed_recipients,
    is_allowed,
    talk_tool_name,
    validate_flows,
)
from .project import ProjectState, project_tools_for
from .roles import build_instructions


class SupportsRun(Protocol):
    """Agency が必要とする最小面: ``await run(text)`` → ``.text`` を持つ応答。
    テストでは scripted fake が置き換える。"""

    async def run(self, message: str) -> Any: ...


class Agency:
    """5 役のエージェント登録簿。通信グラフ・共有状態・通信ログを 1 実行分
    束ねる(元 Agency Swarm の ``Agency`` オブジェクトに対応)。

    エージェントは :meth:`register` で後から登録する — talk ツールは実行時に
    ``agents[recipient]`` を引くクロージャなので、相互参照(CEO のツールが
    CTO を呼び、CTO のツールが developer を呼ぶ)でも構築順の問題が起きない。
    """

    def __init__(
        self,
        *,
        flows: Flows = COMMUNICATION_FLOWS,
        agent_keys: tuple[str, ...] = AGENT_KEYS,
        max_depth: int = DEFAULT_MAX_DEPTH,
        listener: CommListener | None = None,
    ) -> None:
        validate_flows(flows, agent_keys)
        if max_depth < 1:
            raise ValueError("max_depth は 1 以上")
        self.flows: tuple[tuple[str, str], ...] = tuple((s, r) for s, r in flows)
        self.agent_keys = agent_keys
        self.max_depth = max_depth
        self.log = CommLog(listener=listener)
        self.state = ProjectState()
        self._agents: dict[str, SupportsRun] = {}

    # --- 登録簿 -----------------------------------------------------------

    def register(self, key: str, agent: SupportsRun) -> None:
        if key not in self.agent_keys:
            raise KeyError(f"未知のエージェントキー: {key}")
        self._agents[key] = agent

    def agent(self, key: str) -> SupportsRun:
        try:
            return self._agents[key]
        except KeyError:
            raise KeyError(f"エージェント '{key}' が未登録") from None

    # --- 通信(agent-as-tool の実体) -------------------------------------

    def talk_tools(self, sender: str) -> list[Callable[..., Awaitable[str]]]:
        """sender に注入する talk_to_* ツール群を通信グラフから**生成**する。

        許可されたペアの分しか作らない = 非許可ペアにはツール自体が無い。
        """
        return [
            make_talk_tool(self, sender, recipient)
            for recipient in allowed_recipients(sender, self.flows)
        ]

    async def call(self, sender: str, recipient: str, message: str) -> str:
        """sender から recipient への 1 往復(talk ツールの実装)。

        - グラフ検査: ツール生成時点で保証済みだが、防御的に再検査する
        - 深度制御: 上限超過はブロック通知文字列を返す(例外にしない —
          MAF はツール例外の詳細をモデルに見せないため)
        - 記録: 成否によらず CommLog に必ず 1 イベント残す
        """
        if not is_allowed(sender, recipient, self.flows):
            raise PermissionError(
                f"communication_flows に無いペア: {sender} -> {recipient}"
            )
        depth = current_depth() + 1
        if depth > self.max_depth:
            self.log.block(sender, recipient, depth, message)
            return (
                f"[communication blocked] Conversation depth limit ({self.max_depth}) "
                f"reached; your message to {DISPLAY_NAMES.get(recipient, recipient)} was "
                "not delivered. Proceed using your own judgement."
            )
        event = self.log.open(sender, recipient, depth, message)
        with at_depth(depth):
            response = await self.agent(recipient).run(message)
        reply = response.text
        self.log.complete(event, reply)
        return reply

    async def get_response(self, recipient: str, message: str) -> str:
        """トップレベル(user → agent)のターン(元 agency.get_response_sync)。"""
        event = self.log.open("user", recipient, 0, message)
        with at_depth(0):
            response = await self.agent(recipient).run(message)
        reply = response.text
        self.log.complete(event, reply)
        return reply


def make_talk_tool(
    agency: Agency, sender: str, recipient: str
) -> Callable[..., Awaitable[str]]:
    """許可ペア (sender, recipient) の talk_to_<recipient> ツールを生成する。

    MAF の ``Agent(tools=[...])`` は素の callable の ``__name__`` と docstring
    からスキーマを推論するため、両方を動的に与える(元 Agency Swarm の
    SendMessage ツールの recipient 別インスタンス化に対応)。
    """
    display = DISPLAY_NAMES.get(recipient, recipient)

    async def talk(message: str) -> str:
        return await agency.call(sender, recipient, message)

    talk.__name__ = talk_tool_name(recipient)
    talk.__qualname__ = talk.__name__
    talk.__doc__ = (
        f"Send a message to the {display} and get their reply. "
        f"{DESCRIPTIONS.get(recipient, '')}\n\n"
        "Args:\n"
        f"    message: The question or request for the {display}. Include all context"
        " they need; they cannot see your conversation."
    )
    return talk


# --- 実 MAF Agent での組み立て ---------------------------------------------


def build_chat_client(settings: FoundrySettings) -> Any:
    """共有基盤の OpenAI v1 互換エンドポイント+API キーのチャットクライアント。"""
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_agency(
    chat_client: Any,
    *,
    flows: Flows = COMMUNICATION_FLOWS,
    max_depth: int = DEFAULT_MAX_DEPTH,
    listener: CommListener | None = None,
) -> Agency:
    """5 役の実 MAF ``Agent`` を通信グラフに従って組み立てる。

    各エージェントのツール = 役割固有ツール(CEO: analyze_project /
    CTO: create_technical_spec)+ グラフから生成した talk_to_* 群。
    developer / client_manager は出次数 0 なのでツールなし(元アプリと同じ)。
    """
    from agent_framework import Agent

    agency = Agency(flows=flows, max_depth=max_depth, listener=listener)
    for key in AGENT_KEYS:
        tools: list[Any] = [
            *project_tools_for(key, agency.state),
            *agency.talk_tools(key),
        ]
        agency.register(
            key,
            Agent(
                chat_client,
                instructions=build_instructions(key, flows),
                name=key,
                tools=tools or None,
            ),
        )
    return agency
