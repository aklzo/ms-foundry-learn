"""比較検証: agent-framework-orchestrations の ``HandoffBuilder`` で同じ
4 役割リングを組む(examples/handoff_builder_variant.py から実行)。

主実装(workflow.py)との対比が目的。HandoffBuilder は元 AG2 Swarm と同じ
「LLM がツール呼び出しで委譲先を選ぶ」思想だが、本ポートの元アプリが使う
協調機構は素直には載らない:

- **AFTER_WORK(暗黙の制御移譲)がない**: HandoffBuilder の handoff は
  LLM が ``handoff_to_<target>`` ツールを呼んだときだけ発火する。元アプリの
  「応答し終わったら無条件で次へ」は、instructions に「返答の最後に必ず
  handoff ツールを呼べ」と書いてプロンプトで再現するしかない(呼び忘れは
  autonomous mode の nudge 頼み)。
- **context_variables がない**: 共有状態は「全結線メッシュで broadcast される
  会話履歴」そのもの。要約は構造化された状態でなく会話中のテキストとして
  だけ蓄積される。
- **UPDATE_SYSTEM_MESSAGE がない**: participants は build 時に clone される
  静的な ``Agent`` で、ターンごとに instructions を差し替えるフックはない。
  フェーズ(1 周目=要約 / 2 周目=詳細)は「1 回目に話すときは要約、
  2 回目は詳細」と instructions に書き、LLM 自身に会話履歴から現在フェーズを
  数えさせる。
- **終了は max_rounds でなく termination_condition**: 会話全文を受ける述語で
  「## Tech Design が現れたら終了」とする(これは元 max_rounds=13 の暗黙の
  回数調整より頑健だが、one-shot パイプラインに request_info /
  autonomous mode の会話型セマンティクスが付いてくる)。

さらに participants は実 ``Agent`` 限定(clone・ツール注入・middleware 前提)
かつ ``require_per_service_call_history_persistence=True`` が必須のため、
scripted fake による実行のオフラインテストは組めない(構築だけは
オフラインで検証できる → tests/test_handoff_variant.py)。

依存: ``uv sync --extra orchestrations``(agent-framework-orchestrations は
core 外の別パッケージ)。
"""

from __future__ import annotations

from typing import Any

from .prompts import NEXT_ROLE, ROLE_ORDER, SYSTEM_MESSAGES, section_heading

#: 会話にこの見出しが現れたら企画書完成(tech の詳細セクションが最後)
_FINAL_HEADING = section_heading(ROLE_ORDER[-1])


def _agent_name(role: str) -> str:
    return f"{role}_agent"


def _protocol(role: str) -> str:
    """リング+2 周フェーズをプロンプトで再現する協調プロトコル文。

    主実装ではグラフと Executor が決定的に担う内容(リング順・フェーズ判定・
    終了)を、HandoffBuilder では LLM への指示として書くしかない部分。
    """
    next_agent = _agent_name(NEXT_ROLE[role])
    ring = " -> ".join(_agent_name(r) for r in ROLE_ORDER) + f" -> {_agent_name(ROLE_ORDER[0])}"
    lines = [
        "",
        "",
        "Collaboration protocol:",
        (
            f"You are part of a four-designer handoff ring: {ring}. "
            "The conversation itself is the shared context."
        ),
        (
            "- The FIRST time you speak: provide a 2-3 sentence summary of your ideas "
            f"on {role.upper()} based on the context so far. Keep the summary as short "
            f"as possible. Then call the handoff_to_{next_agent} tool."
        ),
        (
            f"- The SECOND time you speak: write the {role} part of the report. Do not "
            "include any other parts. Do not use XML tags. Start your response with: "
            f"'{section_heading(role)}'."
        ),
    ]
    if role == ROLE_ORDER[-1]:
        lines.append(
            "  After writing your detailed section, do NOT call any handoff tool — "
            "the report is complete."
        )
    else:
        lines.append(f"  Then call the handoff_to_{next_agent} tool.")
    return "\n".join(lines)


def build_handoff_variant_agents(chat_client: Any) -> list[Any]:
    """実 ``Agent`` ×4(HandoffBuilder の participants 要件)。

    ``require_per_service_call_history_persistence=True`` は HandoffBuilder の
    build() が全参加者に要求する(handoff ツールを middleware が short-circuit
    するため、サービス側と履歴が食い違わないようにする措置)。
    """
    from agent_framework import Agent

    return [
        Agent(
            chat_client,
            instructions=SYSTEM_MESSAGES[role] + _protocol(role),
            name=_agent_name(role),
            require_per_service_call_history_persistence=True,
        )
        for role in ROLE_ORDER
    ]


def _report_complete(conversation: list[Any]) -> bool:
    """termination_condition: tech の詳細セクションが会話に現れたら終了。"""
    return any(_FINAL_HEADING in (getattr(message, "text", None) or "") for message in conversation)


def build_handoff_variant_workflow(chat_client: Any) -> Any:
    """同じ 4 役割リングを HandoffBuilder で組む。

    - ``add_handoff`` ×4 で既定のメッシュでなく明示リングに制限
      (story→gameplay→visuals→tech→story)
    - ``with_autonomous_mode()``: 既定の human-in-loop(handoff しない応答の
      たびに request_info でユーザー入力を要求)は one-shot パイプラインに
      合わないため、自律継続に切り替える
    - ``with_termination_condition``: 元 max_rounds=13 の代わりに
      「最終セクションの見出しが現れたら終了」
    """
    from agent_framework.orchestrations import HandoffBuilder

    story, gameplay, visuals, tech = build_handoff_variant_agents(chat_client)
    return (
        HandoffBuilder(
            name="game-design-team-handoff-variant",
            participants=[story, gameplay, visuals, tech],
        )
        .add_handoff(story, [gameplay])
        .add_handoff(gameplay, [visuals])
        .add_handoff(visuals, [tech])
        .add_handoff(tech, [story])
        .with_start_agent(story)
        .with_autonomous_mode()
        .with_termination_condition(_report_complete)
        .build()
    )
