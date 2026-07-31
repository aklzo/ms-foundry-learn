"""テスト共有部品: ScriptedAgent(LLM の scripted fake)とクレーム素材。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from claim_voice_live_maf.schemas import ClaimClassification, ClaimNarrative


@dataclass
class FakeResponse:
    text: str
    value: Any = None


class ScriptedAgent:
    """受け取ったメッセージを記録し、決められた応答列を順に返す。

    replies を使い切ったら最後の応答を繰り返す(マルチターン会話テスト用)。
    """

    def __init__(self, replies: list[str | FakeResponse] | str | FakeResponse) -> None:
        if not isinstance(replies, list):
            replies = [replies]
        assert replies, "少なくとも 1 応答が必要"
        self._replies = list(replies)
        self._index = 0
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        self.received.append(message)
        reply = self._replies[min(self._index, len(self._replies) - 1)]
        self._index += 1
        if isinstance(reply, FakeResponse):
            return reply
        return FakeResponse(text=reply)


def complete_flood_claim(**overrides: Any) -> ClaimNarrative:
    """元 examples.py BASEMENT_FLOOD_WITH_PHOTOS 相当の抽出済みクレーム。"""
    data: dict[str, Any] = {
        "policyholder_name": "Maya Singh",
        "policy_number": "H0-44721",
        "contact_method": "415-555-0134 / maya@example.com",
        "date_of_loss": "March 18, 2026",
        "reported_date": "March 19, 2026",
        "loss_location": "Denver",
        "loss_description": "Finished basement flooded after the sump pump failed during heavy rain.",
        "estimated_loss_usd": 18000.0,
        "evidence_available": ["photos", "short video before moving anything"],
        "documents_mentioned": [],
        "raw_narrative_summary": "Basement flood after sump pump failure; photos and video taken.",
    }
    data.update(overrides)
    return ClaimNarrative(**data)


def flood_classification(**overrides: Any) -> ClaimClassification:
    data: dict[str, Any] = {
        "claim_type": "home_water_damage",
        "severity": "medium",
        "severity_rationale": "Moderate water damage with documentation pending.",
        "likely_policy_line": "homeowners",
    }
    data.update(overrides)
    return ClaimClassification(**data)
