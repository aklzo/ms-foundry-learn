"""AG2 Swarm の協調(AfterWork リング+共有 context_variables+動的プロンプト)
を MAF core の明示グラフで再現する。

元アプリの制御フロー(initiate_swarm_chat, max_rounds=13):

    task ─▶ story(要約→update 関数→SwarmResult で gameplay 指名)
         ─▶ gameplay(要約)─▶ visuals(要約)─▶ tech(要約→story 指名)
         ─▶ story(詳細 ## Story Design、AfterWork で gameplay へ)
         ─▶ gameplay(詳細)─▶ visuals(詳細)─▶ tech(詳細)
         ─▶ max_rounds=13 到達で停止 → Streamlit 側が chat_history[-4:] を
            story/gameplay/visuals/tech として拾う

移植後(本モジュール):

    GameDesignContext ─▶ story ─▶ gameplay ─▶ visuals ─▶ tech ─┐
              ▲                                                 │ switch-case
              └──────────[Default: サマリー周回中]──────────────┤
                                                                └─[全セクション
                                                                   完成]─▶ deliver
                                                                        ─▶ GameDesignDocument

- **リング**: AFTER_WORK ×4 と SwarmResult(agent=...) の暗黙の制御移譲を、
  4 本の明示エッジ(tech → story のループエッジ含む)に置き換える。
- **共有状態**: 全エージェントが読める context_variables を、リングを流れる
  ``GameDesignContext`` メッセージ(summaries = context_variables 相当、
  sections = chat_history 末尾 4 件相当)に置き換える。
- **フェーズ判定**: 元は UPDATE_SYSTEM_MESSAGE 内の「自分のキーが None か」。
  移植でも同じ判定を Executor が行う(要約が無ければ要約フェーズ、あれば
  詳細フェーズ)。
- **終了**: 元は max_rounds=13 という回数の暗黙調整(1 task + 8 要約系 +
  4 詳細 = 13)。移植は「全セクションが揃ったら deliver へ」というデータ条件
  の switch-case エッジで、終了が状態から決まる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Never

from agent_framework import Case, Default, Executor, WorkflowBuilder, WorkflowContext, handler

from .agents import GameDesignAgents
from .prompts import ROLE_ORDER, build_section_prompt, build_summary_prompt

# --- グラフを流れるメッセージ ---------------------------------------------


def _empty_roles() -> dict[str, str | None]:
    return dict.fromkeys(ROLE_ORDER)


@dataclass
class GameDesignContext:
    """リングを 2 周する共有コンテキスト。

    ``summaries`` が元アプリの context_variables(update_*_overview が書く
    2-3 文の要約)に対応する。``sections`` は元アプリでは chat_history の
    末尾 4 メッセージとして暗黙に残っていた詳細セクションを、型付きで
    持ち歩くようにしたもの。
    """

    task: str
    summaries: dict[str, str | None] = field(default_factory=_empty_roles)
    sections: dict[str, str | None] = field(default_factory=_empty_roles)

    def all_sections_done(self) -> bool:
        return all(self.sections[role] is not None for role in ROLE_ORDER)


@dataclass
class RoleSummaryDone:
    """進捗イベント(要約フェーズ)。元アプリの
    ``st.sidebar.success('Story overview: ' + ...)`` に対応。"""

    role: str
    summary: str


@dataclass
class RoleSectionDone:
    """進捗イベント(詳細フェーズ)。"""

    role: str
    chars: int


@dataclass
class GameDesignDocument:
    """最終成果物(4 セクションの企画書)。

    元アプリの ``st.session_state.output = {'story': chat_history[-4], ...}``
    (インデックス依存の拾い出し)を型付きフィールドに置き換えたもの。
    """

    task: str
    summaries: dict[str, str]
    sections: dict[str, str]

    def to_markdown(self) -> str:
        parts = ["# Game Concept"]
        parts.extend(self.sections[role] for role in ROLE_ORDER)
        return "\n\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "summaries": dict(self.summaries),
            "sections": dict(self.sections),
        }


# --- Executors -------------------------------------------------------------


class RoleExecutor(Executor):
    """1 役割 = 1 Executor。リングを 2 回通過し、1 周目は要約を、2 周目は
    詳細セクションを context に書き足して次へ渡す。

    元アプリとの対応:
    - フェーズ判定(自分の要約が None か)= UPDATE_SYSTEM_MESSAGE 内の分岐
    - context への書き込み = update_*_overview 関数(元は LLM の関数呼び出し
      +tool_choice 強制。移植では Executor が決定的に行う)
    - 次役割への送信 = SwarmResult(agent=...) / AFTER_WORK(グラフのエッジ)
    """

    def __init__(self, role: str, agents: GameDesignAgents) -> None:
        super().__init__(id=role)
        self._role = role
        self._agent = agents.for_role(role)

    @handler
    async def take_turn(
        self,
        context: GameDesignContext,
        ctx: WorkflowContext[GameDesignContext, RoleSummaryDone | RoleSectionDone],
    ) -> None:
        if context.summaries[self._role] is None:
            await self._summary_turn(context, ctx)
        elif context.sections[self._role] is None:
            await self._section_turn(context, ctx)
        else:
            raise RuntimeError(
                f"{self._role}: 要約もセクションも記入済みの context を受信"
                "(リングの配線か終了条件の誤り)"
            )

    async def _summary_turn(
        self,
        context: GameDesignContext,
        ctx: WorkflowContext[GameDesignContext, RoleSummaryDone | RoleSectionDone],
    ) -> None:
        prompt = build_summary_prompt(self._role, context.task, context.summaries)
        response = await self._agent.run(prompt)
        summary = response.text.strip()
        updated = GameDesignContext(
            task=context.task,
            summaries={**context.summaries, self._role: summary},
            sections=dict(context.sections),
        )
        await ctx.yield_output(RoleSummaryDone(role=self._role, summary=summary))
        await ctx.send_message(updated)

    async def _section_turn(
        self,
        context: GameDesignContext,
        ctx: WorkflowContext[GameDesignContext, RoleSummaryDone | RoleSectionDone],
    ) -> None:
        prompt = build_section_prompt(self._role, context.task, context.summaries)
        response = await self._agent.run(prompt)
        section = response.text.strip()
        updated = GameDesignContext(
            task=context.task,
            summaries=dict(context.summaries),
            sections={**context.sections, self._role: section},
        )
        await ctx.yield_output(RoleSectionDone(role=self._role, chars=len(section)))
        await ctx.send_message(updated)


class DeliverExecutor(Executor):
    """完成した context から最終企画書を組み立てる。

    元アプリではこの工程は swarm の外(Streamlit 側)にあり、
    ``result.chat_history[-4:]`` というインデックス依存の拾い出しだった。
    max_rounds=13 が 1 ターンでもずれると壊れる暗黙の結合を、
    「全セクションが揃った context を型どおり詰め替える」に置き換える。
    """

    def __init__(self) -> None:
        super().__init__(id="deliver")

    @handler
    async def deliver(
        self, context: GameDesignContext, ctx: WorkflowContext[Never, GameDesignDocument]
    ) -> None:
        missing = [role for role in ROLE_ORDER if context.sections[role] is None]
        if missing:
            raise RuntimeError(f"deliver: セクション未完成のまま到達: {missing}")
        await ctx.yield_output(
            GameDesignDocument(
                task=context.task,
                summaries={role: context.summaries[role] or "" for role in ROLE_ORDER},
                sections={role: context.sections[role] or "" for role in ROLE_ORDER},
            )
        )


# --- 組み立て ---------------------------------------------------------------


def build_game_design_workflow(agents: GameDesignAgents):
    """``await workflow.run(GameDesignContext(task=...))`` で実行する
    リング型ワークフローを組み立てる。進捗は ``stream=True`` の intermediate
    イベント(RoleSummaryDone / RoleSectionDone)。"""
    story, gameplay, visuals, tech = (RoleExecutor(role, agents) for role in ROLE_ORDER)
    deliver = DeliverExecutor()

    return (
        WorkflowBuilder(
            start_executor=story,
            output_from=[deliver],
            intermediate_output_from=[story, gameplay, visuals, tech],
        )
        .add_edge(story, gameplay)
        .add_edge(gameplay, visuals)
        .add_edge(visuals, tech)
        # tech の後: 全セクション完成なら deliver、そうでなければ story へ戻る
        # ループエッジ(元アプリの AFTER_WORK(story_agent) と max_rounds=13 の
        # 回数調整を、データ条件による明示分岐に置き換える)
        .add_switch_case_edge_group(
            tech,
            [
                Case(
                    condition=lambda msg: isinstance(msg, GameDesignContext)
                    and msg.all_sections_done(),
                    target=deliver,
                ),
                Default(target=story),
            ],
        )
        .build()
    )
