"""GameSpec(元 Streamlit フォーム)とタスク文組み立てのテスト。"""

import json

from game_design_team_maf.spec import GameSpec


def test_defaults_match_streamlit_widget_initials() -> None:
    spec = GameSpec()
    assert spec.background_vibe == "Epic fantasy with dragons"
    assert spec.game_type == "RPG"
    assert spec.game_goal == "Save the kingdom from eternal winter"
    assert spec.target_audience == "Kids (7-12)"
    assert spec.development_time_months == 12
    assert spec.budget_usd == 10_000
    assert spec.depth == "Low"


def test_to_task_reproduces_original_fstring_fields() -> None:
    spec = GameSpec(
        platforms=("PC", "Nintendo Switch"),
        core_mechanics=("Combat", "Exploration"),
        mood=("Epic", "Mysterious"),
        inspiration="Zelda",
        unique_features="Dragon bonding",
        budget_usd=250_000,
    )
    task = spec.to_task()
    assert task.startswith("Create a game concept with the following details:")
    assert "- Background Vibe: Epic fantasy with dragons" in task
    assert "- Target Platforms: PC, Nintendo Switch" in task
    assert "- Budget: $250,000" in task  # 元の f"${cost:,}" 書式
    assert "- Core Mechanics: Combat, Exploration" in task
    assert "- Mood/Atmosphere: Epic, Mysterious" in task
    assert "- Inspiration: Zelda" in task
    assert "- Unique Features: Dragon bonding" in task
    assert "- Detail Level: Low" in task


def test_to_dict_is_json_serializable() -> None:
    payload = json.loads(json.dumps(GameSpec(platforms=("PC",)).to_dict()))
    assert payload["platforms"] == ["PC"]
    assert payload["budget_usd"] == 10_000
