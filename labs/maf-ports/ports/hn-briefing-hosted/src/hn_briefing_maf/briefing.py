"""ブリーフの決定論部分 — digest レンダリングと Brief ペイロード。

元実装(scout.py render_brief)は text と HTML の両方を決定論レンダリング
していた(LLM 不使用)。移植後の分担:

- **決定論部分(本モジュール)**: ランク済み記事の digest テキスト
  (タイトル / signal note / points・comments・rank / リンク)と件名。
  LLM への入力とオフライン検証の両方に使う
- **LLM 部分(workflow.py の brief 段)**: digest から「なぜ重要か」と
  Next actions を編集したブリーフ本文(brief_md)を生成 — 元の静的
  next_actions リスト+定型 summary を LLM の編集に置き換えた移植差分

HTML レンダリングは配信(Gmail/webhook)ごとスコープ外のため落とした
(README の設計判断参照)。タイムゾーンは元実装の Pacific 基準を踏襲。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any
from zoneinfo import ZoneInfo

from .hn import Story

#: 元実装の基準タイムゾーン(scout.py の PACIFIC)をそのまま踏襲
PACIFIC = ZoneInfo("America/Los_Angeles")

EMPTY_DIGEST_LINE = "No high-signal agent-building stories found."


def subject_for(now: dt.datetime) -> str:
    """件名(元実装の文言を保存)。"""
    return f"AgentScout Hacker News brief - {now.strftime('%Y-%m-%d')}"


def render_digest(stories: list[Story]) -> str:
    """ランク済み記事の決定論 digest(元 render_brief の text 部の核)。"""
    lines = ["Highest-signal agent-building stories:", ""]
    for index, story in enumerate(stories, start=1):
        signal = f"{story.points} points, {story.comments} comments, front-page rank {story.rank}"
        lines.extend(
            [
                f"{index}. {story.title}",
                f"   Signal note: {story.summary}",
                f"   Signal: {signal}",
                f"   Link: {story.url}",
                f"   HN: {story.hn_url}",
                "",
            ]
        )
    if not stories:
        lines.append(EMPTY_DIGEST_LINE)
    return "\n".join(lines)


@dataclass(frozen=True)
class Brief:
    """最終成果物(元 Brief の text/html を digest_text/brief_md に再編)。"""

    generated_at: str
    subject: str
    digest_text: str
    brief_md: str
    stories: list[Story]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["stories"] = [asdict(story) for story in self.stories]
        return payload


def build_brief(
    stories: list[Story],
    brief_md: str,
    *,
    now: dt.datetime | None = None,
) -> Brief:
    now = now or dt.datetime.now(PACIFIC)
    return Brief(
        generated_at=now.isoformat(timespec="seconds"),
        subject=subject_for(now),
        digest_text=render_digest(stories),
        brief_md=brief_md,
        stories=stories,
    )
