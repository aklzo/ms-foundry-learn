"""テキスト対話層: 会話ターンの蓄積と FNOL コアの毎ターン実行。

元アプリの live_demo/server.py の ``IntakeSession`` + ``_process_with_adk_graph``
に対応する(FastAPI/WebSocket の転送面を除いた中身)。設計は元と同じ:

- 会話は Claimant / Agent のターン列。エージェントの応答は LLM の自由生成では
  なく、決定論パケットの ``claimant_next_message``(次に聞くべき質問)を使う
- 毎ターン、**請求者発話の全文**をコアに流して状態を作り直す(漸進構築 =
  transcript の伸長)

ライブスモーク(pytest -m live)はこの層+実モデルで完結する。Voice Live 層
(voice.py / scripts/voice_session.py)はこの層と同じコアを音声の外側に被せる。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .agents import ClaimIntakeAgents
from .policies import build_intake_state
from .schemas import IntakeState
from .workflow import StageDone, run_intake_turn

#: 元 server.py の初回エージェント発話(安全確認から始める)。
GREETING = (
    "I can start the claim while we talk. First, are you and everyone else in a safe place?"
)


@dataclass
class Turn:
    speaker: str  # "Claimant" | "Agent"
    text: str


@dataclass
class ClaimIntakeConversation:
    """1 セッション分の会話状態。"""

    agents: ClaimIntakeAgents
    transcript: list[Turn] = field(default_factory=list)
    state: IntakeState = field(default_factory=build_intake_state)

    def __post_init__(self) -> None:
        if not self.transcript:
            self.transcript.append(Turn(speaker="Agent", text=GREETING))

    def claimant_text(self) -> str:
        """ここまでの請求者発話の全文(コアへの入力。元 _claimant_text)。"""
        return "\n".join(turn.text for turn in self.transcript if turn.speaker == "Claimant")

    async def claimant_turn(
        self,
        text: str,
        on_stage: Callable[[StageDone], None] | None = None,
    ) -> IntakeState:
        """請求者の 1 発話を取り込み、コアを実行し、次の質問を応答として積む。"""
        cleaned = text.strip()
        if not cleaned:
            return self.state
        self.transcript.append(Turn(speaker="Claimant", text=cleaned))
        self.state = await run_intake_turn(self.agents, self.claimant_text(), on_stage=on_stage)
        self.transcript.append(Turn(speaker="Agent", text=self.state.next_question))
        return self.state


async def run_script(
    conversation: ClaimIntakeConversation,
    lines: Iterable[str],
    on_state: Callable[[str, IntakeState], None] | None = None,
) -> IntakeState:
    """スクリプト(請求者発話のリスト)を順に再生する。"""
    for line in lines:
        state = await conversation.claimant_turn(line)
        if on_state is not None:
            on_state(line, state)
    return conversation.state


def load_script(path: Path) -> list[str]:
    """スクリプトファイルを読む。1 行 = 請求者の 1 発話。空行と # 行は無視。"""
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines
