"""動的プロンプトの組み立て(元アプリの ``UPDATE_SYSTEM_MESSAGE`` の移植)。

元アプリの ``update_system_message_func`` は毎ターン、
1. 役割の base system message(``system_messages[agent.name]``)に、
2. フェーズ別の指示 — 自分の context_variables キーが未記入なら「update 関数を
   呼んで 2-3 文の要約を出せ」(tool_choice で関数呼び出しを強制)、記入済みなら
   「'## X Design' で始まる詳細セクションを書け」(tools を外し、履歴を先頭の
   task 1 件に切り詰め)、
3. 「Below are some context for you to refer to:」+ 記入済みサマリー一覧、
を連結して system prompt を差し替えていた。

移植では役割ペルソナ(1)を MAF ``Agent`` の静的 instructions に置き、
フェーズ指示(2)+コンテキスト(3)+タスク文を **実行のたびに文字列として
組み立てて ``Agent.run`` に渡す**。MAF の Agent.run は毎回ステートレスなので、
「system message を動的に差し替える」機構そのものが不要になる(README 学び)。

文言は原文を極力踏襲する(「You task is write ...」の typo も原文どおり)。
差分は要約フェーズのみ: 元は tool_choice で update 関数の呼び出しを強制して
引数 ``story_summary`` を要約として回収していたが、移植では応答テキスト
そのものを要約として回収するため、「update 関数を呼べ」を「要約だけを
返せ」に置き換えた。
"""

from __future__ import annotations

#: リングの順序(元アプリの AFTER_WORK 登録順 = story → gameplay → visuals →
#: tech → story)。
ROLE_ORDER: tuple[str, ...] = ("story", "gameplay", "visuals", "tech")

#: 次の役割(AFTER_WORK のハンドオフ・リング)。tech → story のループを含む。
NEXT_ROLE: dict[str, str] = {
    role: ROLE_ORDER[(i + 1) % len(ROLE_ORDER)] for i, role in enumerate(ROLE_ORDER)
}

#: 元アプリの system_messages(原文そのまま。インデントのみ除去)。
SYSTEM_MESSAGES: dict[str, str] = {
    "story": (
        "You are an experienced game story designer specializing in narrative design "
        "and world-building. Your task is to:\n"
        "1. Create a compelling narrative that aligns with the specified game type and "
        "target audience.\n"
        "2. Design memorable characters with clear motivations and character arcs.\n"
        "3. Develop the game's world, including its history, culture, and key locations.\n"
        "4. Plan story progression and major plot points.\n"
        "5. Integrate the narrative with the specified mood/atmosphere.\n"
        "6. Consider how the story supports the core gameplay mechanics."
    ),
    "gameplay": (
        "You are a senior game mechanics designer with expertise in player engagement "
        "and systems design. Your task is to:\n"
        "1. Design core gameplay loops that match the specified game type and mechanics.\n"
        "2. Create progression systems (character development, skills, abilities).\n"
        "3. Define player interactions and control schemes for the chosen perspective.\n"
        "4. Balance gameplay elements for the target audience.\n"
        "5. Design multiplayer interactions if applicable.\n"
        "6. Specify game modes and difficulty settings.\n"
        "7. Consider the budget and development time constraints."
    ),
    "visuals": (
        "You are a creative art director with expertise in game visual and audio design. "
        "Your task is to:\n"
        "1. Define the visual style guide matching the specified art style.\n"
        "2. Design character and environment aesthetics.\n"
        "3. Plan visual effects and animations.\n"
        "4. Create the audio direction including music style, sound effects, and ambient "
        "sound.\n"
        "5. Consider technical constraints of chosen platforms.\n"
        "6. Align visual elements with the game's mood/atmosphere.\n"
        "7. Work within the specified budget constraints."
    ),
    "tech": (
        "You are a technical director with extensive game development experience. "
        "Your task is to:\n"
        "1. Recommend appropriate game engine and development tools.\n"
        "2. Define technical requirements for all target platforms.\n"
        "3. Plan the development pipeline and asset workflow.\n"
        "4. Identify potential technical challenges and solutions.\n"
        "5. Estimate resource requirements within the budget.\n"
        "6. Consider scalability and performance optimization.\n"
        "7. Plan for multiplayer infrastructure if applicable."
    ),
}


def section_heading(role: str) -> str:
    """詳細セクションの見出し(元: ``f"## {current_gen.capitalize()} Design"``)。"""
    return f"## {role.capitalize()} Design"


def context_block(summaries: dict[str, str | None]) -> str:
    """記入済みサマリーの一覧(元アプリの context_variables 差し込み部の原文)。

    元と同じく、ヘッダ行は常に付き、記入済みのキーだけが
    ``{k.capitalize()} Summary:`` として続く(全員未記入ならヘッダのみ)。
    """
    block = "Below are some context for you to refer to:"
    for role in ROLE_ORDER:
        summary = summaries.get(role)
        if summary is not None:
            block += f"\n{role.capitalize()} Summary:\n{summary}"
    return block


def build_summary_prompt(role: str, task: str, summaries: dict[str, str | None]) -> str:
    """要約フェーズ(1 周目)の実行プロンプト。

    元: ``system_prompt += f"Call the update function provided to first provide a
    2-3 sentence summary of your ideas on {current_gen.upper()} based on the
    context provided."`` + tool_choice 強制。移植では update 関数がない
    (context への書き込みは Executor が決定的に行う)ため、要約テキスト
    そのものを返させる。
    """
    return (
        f"First provide a 2-3 sentence summary of your ideas on {role.upper()} "
        "based on the context provided. Keep the summary as short as possible. "
        "Reply with the summary text only.\n"
        "\n"
        f"{context_block(summaries)}\n"
        "\n"
        f"{task}"
    )


def build_section_prompt(role: str, task: str, summaries: dict[str, str | None]) -> str:
    """詳細フェーズ(2 周目)の実行プロンプト。

    元(原文・typo 含む): ``"\\n\\nYour task\\nYou task is write the {current_gen}
    part of the report. Do not include any other parts. Do not use XML tags.\\n
    Start your response with: '## {current_gen.capitalize()} Design'."``

    元アプリはこのフェーズで会話履歴を先頭の task 1 件に切り詰めていた
    (コスト削減)。MAF の Agent.run は毎回ステートレスなので、この挙動は
    「プロンプトに task と全サマリーだけを入れる」ことで自然に一致する。
    """
    return (
        "Your task\n"
        f"You task is write the {role} part of the report. Do not include any "
        "other parts. Do not use XML tags.\n"
        f"Start your response with: '{section_heading(role)}'.\n"
        "\n"
        f"{context_block(summaries)}\n"
        "\n"
        f"{task}"
    )
