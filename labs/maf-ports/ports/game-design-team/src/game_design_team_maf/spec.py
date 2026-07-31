"""ゲーム仕様(元アプリの Streamlit フォーム入力)と初期タスク文の組み立て。

元アプリはサイドバー+2 カラムのフォームで 15 項目を集め、f-string で
「Create a game concept with the following details:」のタスク文を組み立てて
``initiate_swarm_chat(messages=task)`` に渡していた。CLI 化では同じ 15 項目を
デフォルト付きのフラグにし、タスク文のフォーマットは原文を踏襲する
(既定値は Streamlit ウィジェットの初期値と同じ)。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GameSpec:
    """元アプリのフォーム 15 項目。既定値は Streamlit ウィジェットの初期値。"""

    background_vibe: str = "Epic fantasy with dragons"
    game_type: str = "RPG"
    game_goal: str = "Save the kingdom from eternal winter"
    target_audience: str = "Kids (7-12)"
    player_perspective: str = "First Person"
    multiplayer: str = "Single Player Only"
    art_style: str = "Realistic"
    platforms: tuple[str, ...] = ()
    development_time_months: int = 12
    budget_usd: int = 10_000
    core_mechanics: tuple[str, ...] = ()
    mood: tuple[str, ...] = ()
    inspiration: str = ""
    unique_features: str = ""
    depth: str = "Low"

    def to_task(self) -> str:
        """元アプリの task f-string(原文のフィールド並び・書式)を再現する。"""
        return (
            "Create a game concept with the following details:\n"
            f"- Background Vibe: {self.background_vibe}\n"
            f"- Game Type: {self.game_type}\n"
            f"- Game Goal: {self.game_goal}\n"
            f"- Target Audience: {self.target_audience}\n"
            f"- Player Perspective: {self.player_perspective}\n"
            f"- Multiplayer Support: {self.multiplayer}\n"
            f"- Art Style: {self.art_style}\n"
            f"- Target Platforms: {', '.join(self.platforms)}\n"
            f"- Development Time: {self.development_time_months} months\n"
            f"- Budget: ${self.budget_usd:,}\n"
            f"- Core Mechanics: {', '.join(self.core_mechanics)}\n"
            f"- Mood/Atmosphere: {', '.join(self.mood)}\n"
            f"- Inspiration: {self.inspiration}\n"
            f"- Unique Features: {self.unique_features}\n"
            f"- Detail Level: {self.depth}"
        )

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["platforms"] = list(self.platforms)
        data["core_mechanics"] = list(self.core_mechanics)
        data["mood"] = list(self.mood)
        return data
