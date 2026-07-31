"""動的プロンプト組み立て(UPDATE_SYSTEM_MESSAGE 移植)の単体テスト。"""

from game_design_team_maf.prompts import (
    NEXT_ROLE,
    ROLE_ORDER,
    SYSTEM_MESSAGES,
    build_section_prompt,
    build_summary_prompt,
    context_block,
    section_heading,
)

TASK = "Create a game concept with the following details:\n- Background Vibe: test"


def test_role_order_matches_afterwork_ring() -> None:
    assert ROLE_ORDER == ("story", "gameplay", "visuals", "tech")
    assert NEXT_ROLE == {
        "story": "gameplay",
        "gameplay": "visuals",
        "visuals": "tech",
        "tech": "story",  # 元アプリの AFTER_WORK(story_agent) のループ
    }


def test_system_messages_cover_all_roles_with_original_personas() -> None:
    assert set(SYSTEM_MESSAGES) == set(ROLE_ORDER)
    assert "game story designer" in SYSTEM_MESSAGES["story"]
    assert "game mechanics designer" in SYSTEM_MESSAGES["gameplay"]
    assert "creative art director" in SYSTEM_MESSAGES["visuals"]
    assert "technical director" in SYSTEM_MESSAGES["tech"]


def test_context_block_empty_has_header_only() -> None:
    """全員未記入でもヘッダ行は付く(元実装の挙動を踏襲)。"""
    block = context_block(dict.fromkeys(ROLE_ORDER))
    assert block == "Below are some context for you to refer to:"


def test_context_block_lists_only_filled_summaries_in_role_order() -> None:
    summaries = dict.fromkeys(ROLE_ORDER)
    summaries["story"] = "S1"
    summaries["visuals"] = "V1"
    block = context_block(summaries)
    assert "Story Summary:\nS1" in block
    assert "Visuals Summary:\nV1" in block
    assert "Gameplay Summary:" not in block
    assert "Tech Summary:" not in block
    assert block.index("Story Summary:") < block.index("Visuals Summary:")


def test_summary_prompt_contains_phase_instruction_context_and_task() -> None:
    summaries = dict.fromkeys(ROLE_ORDER)
    summaries["story"] = "S1"
    prompt = build_summary_prompt("gameplay", TASK, summaries)
    assert "2-3 sentence summary of your ideas on GAMEPLAY" in prompt
    assert "Keep the summary as short as possible" in prompt  # 元 update 関数の docstring
    assert "Story Summary:\nS1" in prompt
    assert TASK in prompt


def test_section_prompt_contains_original_wording_including_typo() -> None:
    summaries = {role: f"{role}-sum" for role in ROLE_ORDER}
    prompt = build_section_prompt("tech", TASK, summaries)
    # 元アプリの原文(「You task is write ...」の typo 含む)を踏襲
    assert "Your task\nYou task is write the tech part of the report." in prompt
    assert "Do not include any other parts. Do not use XML tags." in prompt
    assert "Start your response with: '## Tech Design'." in prompt
    for role in ROLE_ORDER:
        assert f"{role}-sum" in prompt
    assert TASK in prompt


def test_section_heading_capitalizes_role() -> None:
    assert section_heading("story") == "## Story Design"
    assert section_heading("tech") == "## Tech Design"
