"""エージェント間通信の構造化記録(CommLog)と再帰深度の制御。

元 Agency Swarm では SendMessage ツールの発火はフレームワーク内部のスレッド
管理に埋もれ、「誰が誰に何を聞いたか」は外から見えない。移植では通信 1 件を
:class:`CommEvent` として必ず記録する — これがトレース(App Insights の
execute_tool / invoke_agent 入れ子スパン)と並ぶ本ポートの見どころ。

再帰深度: 元実装に上限はない(Agency Swarm はグラフが循環しない限り実質
有限)。移植は ``contextvars.ContextVar`` で「いま何ホップ目の会話の中か」を
追跡し、既定 :data:`DEFAULT_MAX_DEPTH` = 3 で打ち切る。ContextVar なので
LLM が並列ツール呼び出しを出して asyncio が分岐しても枝ごとに正しく数えられ、
打ち切り時はツールが**ブロック通知文字列を返す**(例外にしない — MAF は
ツール例外を "Error: Function failed." に丸めるため、モデルに理由が伝わる形
を選ぶ)。

深度の定義: トップレベル(user → agent)= 0、そこからの相談 1 ホップ目 = 1。
実グラフ(flows.py)は DAG 最長 2 ホップなので深度 3 は安全弁である。
なお深度は「連鎖の深さ」だけを制限し、同一深度での呼び出し**回数**(幅)は
制限しない — 幅の上限は MAF 側の max_iterations が実質的に担う。
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

#: トップレベル呼び出し(元 agency.get_response)の sender 表記
USER = "user"

#: 再帰深度の既定上限(元実装に上限なし → 移植側の判断で 3)
DEFAULT_MAX_DEPTH = 3

_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar(
    "services_agency_comm_depth", default=0
)


def current_depth() -> int:
    """現在のタスク文脈の会話深度(0 = トップレベル)。"""
    return _DEPTH.get()


@contextmanager
def at_depth(depth: int) -> Iterator[None]:
    """このブロック内の会話深度を ``depth`` に固定する。"""
    token = _DEPTH.set(depth)
    try:
        yield
    finally:
        _DEPTH.reset(token)


@dataclass
class CommEvent:
    """通信 1 件の構造化記録。

    ``blocked=True`` は深度上限で相手に**届かなかった**試行(reply は None の
    まま)。``sender == USER`` はトップレベルターン。
    """

    seq: int
    sender: str
    recipient: str
    depth: int
    message: str
    reply: str | None = None
    blocked: bool = False

    @property
    def pair(self) -> tuple[str, str]:
        return (self.sender, self.recipient)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "sender": self.sender,
            "recipient": self.recipient,
            "depth": self.depth,
            "message": self.message,
            "reply": self.reply,
            "blocked": self.blocked,
        }

    def render(self) -> str:
        indent = "  " * self.depth
        if self.blocked:
            status = "BLOCKED (depth limit)"
        elif self.reply is None:
            status = "(pending)"
        else:
            status = f"reply {len(self.reply)} chars"
        summary = self.message.replace("\n", " ")
        if len(summary) > 80:
            summary = summary[:77] + "..."
        return (
            f"{indent}#{self.seq} {self.sender} -> {self.recipient} "
            f"[depth={self.depth}] {summary!r} => {status}"
        )


#: listener のフェーズ: "ask"(開始)/ "reply"(応答確定)/ "blocked"(打ち切り)
CommListener = Callable[[CommEvent, str], None]


class CommLog:
    """通信イベントの追記専用ログ。listener で CLI の逐次表示にも使う。"""

    def __init__(self, listener: CommListener | None = None) -> None:
        self._events: list[CommEvent] = []
        self._listener = listener

    def _notify(self, event: CommEvent, phase: str) -> None:
        if self._listener is not None:
            self._listener(event, phase)

    def open(self, sender: str, recipient: str, depth: int, message: str) -> CommEvent:
        event = CommEvent(
            seq=len(self._events) + 1,
            sender=sender,
            recipient=recipient,
            depth=depth,
            message=message,
        )
        self._events.append(event)
        self._notify(event, "ask")
        return event

    def complete(self, event: CommEvent, reply: str) -> None:
        event.reply = reply
        self._notify(event, "reply")

    def block(self, sender: str, recipient: str, depth: int, message: str) -> CommEvent:
        event = CommEvent(
            seq=len(self._events) + 1,
            sender=sender,
            recipient=recipient,
            depth=depth,
            message=message,
            blocked=True,
        )
        self._events.append(event)
        self._notify(event, "blocked")
        return event

    @property
    def events(self) -> tuple[CommEvent, ...]:
        return tuple(self._events)

    def agent_pairs(self, include_blocked: bool = False) -> list[tuple[str, str]]:
        """エージェント間通信の (sender, recipient) 列(トップレベルは除く)。"""
        return [
            event.pair
            for event in self._events
            if event.sender != USER and (include_blocked or not event.blocked)
        ]

    def to_dicts(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._events]

    def render(self) -> str:
        if not self._events:
            return "(no communications)"
        return "\n".join(event.render() for event in self._events)
