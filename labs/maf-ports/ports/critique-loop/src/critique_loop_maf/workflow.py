"""批評・改善ループを MAF workflow のサイクリックグラフで表現する。

元アプリの制御フロー(streamlit_app.py):

    generate_initial_answer: 3 候補を ThreadPoolExecutor で並列生成 → 統合
    for iteration in range(max_iterations):   # スライダー 1-3、既定 2
        critique_answer(current)              # '•' 箇条書きの自由テキスト
        revise_answer(current, critiques)     # 無条件に改訂
    final = current                           # 最後の改訂は批評されない

移植後(本モジュール):

                ┌─▶ candidate(structured)─┐
    prompt ──▶ dispatcher ─▶ candidate(practical) ─┼─▶ synthesize ─▶ critic ─┐
                └─▶ candidate(skeptical) ─┘                    ▲             │ switch-case
                                                               │             ├─[accept or
                                                    revise ◀───┴─[revise]────┤  上限到達]
                                                    (ループエッジ)           └─▶ finalize
                                                                              ─▶ CritiqueLoopResult

- **fan-out/fan-in**: 元の ThreadPoolExecutor を ``add_fan_out_edges`` /
  ``add_fan_in_edges`` に置き換える(Port 2 と同じ。fan-in はエッジ定義順で
  決定的)。
- **ループ**: 元の ``for range(max_iterations)`` を revise → critic の
  ループエッジ+switch-case のデータ条件に置き換える(Port 7 と同じ翻訳)。
  上限は ``LoopState.max_rounds``(既定 2、1〜3 — 元スライダーと同一)で、
  改訂数が上限に達したら critic は **LLM を呼ばずに** 打ち切る — 元実装が
  「最後の改訂を批評しない」のと同じ呼び出し回数になる。
- **早期終了(元との差分)**: 元は無条件に max_iterations 回改訂した。移植は
  批評を構造化出力(CritiqueVerdict)にし、``verdict="accept"`` なら改訂せず
  終了する。上限は元と同じなので、悪化しない方向の差分(README 参照)。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Never

from agent_framework import Case, Default, Executor, WorkflowBuilder, WorkflowContext, handler

from .agents import CritiqueLoopAgents
from .schemas import CritiqueVerdict, SchemaError, parse_structured

#: 元アプリの max_iterations スライダー(1〜3、既定 2)
DEFAULT_MAX_ROUNDS = 2
MIN_MAX_ROUNDS = 1
MAX_MAX_ROUNDS = 3

#: 停止理由
STOP_ACCEPTED = "accepted"  # 批評が accept(早期終了 — 移植で追加)
STOP_MAX_ROUNDS = "max-rounds"  # 改訂数が上限到達(元実装の唯一の停止条件)


# --- 元アプリのプロンプト(原文)------------------------------------------


def synthesis_prompt(candidate_answers: list[str]) -> str:
    """generate_initial_answer の統合プロンプト原文(候補数だけ動的)。"""
    candidate_texts = [
        f"--- Candidate {i + 1} ---\n{answer}" for i, answer in enumerate(candidate_answers)
    ]
    return (
        f"You are given {len(candidate_answers)} candidate answers. "
        "Synthesize them into ONE best answer, "
        "eliminating repetition and ensuring coherence:\n\n"
        f"{chr(10).join(candidate_texts)}\n\n"
        "Return the single best final answer."
    )


def critique_prompt(prompt: str, answer: str) -> str:
    """critique_answer のプロンプト。前半は原文、末尾の出力形式だけ
    「'•' 箇条書き」→「構造化出力(継続/終了判断+改善指示)」に置換。"""
    return (
        f"Original question: {prompt}\n\n"
        f"Answer to critique:\n{answer}\n\n"
        "Act as a critical reviewer. List specific flaws, missing information, "
        "unclear explanations, or areas that need improvement. Be constructive but thorough. "
        "Then decide whether another revision is worthwhile:\n"
        '- If the answer is already high quality, return {"verdict": "accept", "critiques": []}.\n'
        '- Otherwise return {"verdict": "revise", "critiques": [...]} where each entry is one '
        "specific, actionable improvement instruction.\n"
        "Return ONLY the JSON object."
    )


def revision_prompt(prompt: str, original_answer: str, critiques: list[str]) -> str:
    """revise_answer のプロンプト原文。構造化された批評リストを元アプリの
    「'•' 箇条書き」形式に戻して埋め込む(改訂プロンプトに批評が含まれる
    ことはオフラインテストの検証項目)。"""
    critique_text = "\n".join(f"• {critique}" for critique in critiques)
    return (
        f"Original question: {prompt}\n\n"
        f"Original answer:\n{original_answer}\n\n"
        f"Critiques to address:\n{critique_text}\n\n"
        "Revise the original answer to address every critique point. "
        "Maintain the good parts, fix the issues, and add missing information. "
        "Return the improved answer."
    )


# --- グラフを流れるメッセージ ---------------------------------------------


@dataclass
class CandidateRequest:
    """dispatcher → 各 candidate(fan-out で全員に同一内容が届く)。"""

    prompt: str
    max_rounds: int


@dataclass
class CandidateReply:
    """candidate → synthesize(fan-in で list に束ねられる)。"""

    prompt: str
    max_rounds: int
    name: str
    answer: str


@dataclass
class Revision:
    """改善 1 周分の記録(元の results["iterations"] の improvement 要素)。

    ``critiques`` はこの改訂が対処した批評(= 直前ドラフトへの批評)。
    """

    round: int
    critiques: list[str]
    answer: str


@dataclass
class LoopState:
    """synthesize → critic、revise → critic(ループエッジ)を流れる状態。

    元アプリの current_answer + results["iterations"] に対応。上限
    ``max_rounds`` をデータとして運び、critic の打ち切り判断(データ条件)に
    使う(Port 7 の GameDesignContext と同じ型)。
    """

    prompt: str
    draft: str
    initial_draft: str
    candidates: list[CandidateReply]
    revisions: list[Revision] = field(default_factory=list)
    max_rounds: int = DEFAULT_MAX_ROUNDS

    def exhausted(self) -> bool:
        return len(self.revisions) >= self.max_rounds


@dataclass
class CritiqueOutcome:
    """critic → 分岐(revise / finalize)。

    ``verdict``: "revise"(改訂へ)/ "accept"(合格 — 早期終了)/
    "max-rounds"(上限到達 — LLM 未呼び出しの打ち切り)。
    """

    state: LoopState
    verdict: str
    critiques: list[str] = field(default_factory=list)


# --- 進捗イベント(元アプリの st.spinner / expander 相当)------------------


@dataclass
class CandidateDone:
    name: str
    chars: int


@dataclass
class DraftSynthesized:
    chars: int


@dataclass
class CritiqueDecided:
    """critic の判断。round は「これから行う改善周回」の番号(1 始まり)。"""

    round: int
    verdict: str
    critique_count: int


@dataclass
class RevisionDone:
    round: int
    chars: int


@dataclass
class CritiqueLoopResult:
    """最終成果物(元の results dict に対応。型付き+停止理由を追加)。"""

    prompt: str
    final_answer: str
    initial_answer: str
    candidates: list[CandidateReply]
    revisions: list[Revision]
    stop_reason: str  # STOP_ACCEPTED | STOP_MAX_ROUNDS
    max_rounds: int

    @property
    def total_iterations(self) -> int:
        """元アプリの results["total_iterations"](初稿 1 + 改善周回数)。"""
        return 1 + len(self.revisions)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_iterations"] = self.total_iterations
        return data


# --- Executors -------------------------------------------------------------


class DispatcherExecutor(Executor):
    """str 入力を CandidateRequest に持ち上げてファンアウトの起点になる。"""

    def __init__(self, max_rounds: int) -> None:
        super().__init__(id="dispatcher")
        self._max_rounds = max_rounds

    @handler
    async def dispatch(self, prompt: str, ctx: WorkflowContext[CandidateRequest]) -> None:
        await ctx.send_message(CandidateRequest(prompt=prompt, max_rounds=self._max_rounds))


class CandidateExecutor(Executor):
    """候補 1 体の生成(元の _one_completion(temperature=0.9) ×3 の 1 本)。"""

    def __init__(self, name: str, agent: Any) -> None:
        super().__init__(id=f"candidate_{name}")
        self._name = name
        self._agent = agent

    @handler
    async def generate(
        self, request: CandidateRequest, ctx: WorkflowContext[CandidateReply, CandidateDone]
    ) -> None:
        response = await self._agent.run(request.prompt)
        answer = response.text
        await ctx.yield_output(CandidateDone(name=self._name, chars=len(answer)))
        await ctx.send_message(
            CandidateReply(
                prompt=request.prompt,
                max_rounds=request.max_rounds,
                name=self._name,
                answer=answer,
            )
        )


class SynthesizeExecutor(Executor):
    """fan-in の合流点。全候補を 1 プロンプトに束ねて初稿に統合する
    (元の generate_initial_answer 後半)。"""

    def __init__(self, agents: CritiqueLoopAgents) -> None:
        super().__init__(id="synthesize")
        self._agents = agents

    @handler
    async def synthesize(
        self, replies: list[CandidateReply], ctx: WorkflowContext[LoopState, DraftSynthesized]
    ) -> None:
        prompt = synthesis_prompt([reply.answer for reply in replies])
        response = await self._agents.synthesizer.run(prompt)
        draft = response.text
        await ctx.yield_output(DraftSynthesized(chars=len(draft)))
        await ctx.send_message(
            LoopState(
                prompt=replies[0].prompt,
                draft=draft,
                initial_draft=draft,
                candidates=list(replies),
                max_rounds=replies[0].max_rounds,
            )
        )


class CriticExecutor(Executor):
    """批評+継続/終了判断(元の critique_answer + for ループの残回数管理)。

    - 改訂数が上限(state.max_rounds)に達していたら **LLM を呼ばずに**
      "max-rounds" で打ち切る — 元実装が最後の改訂を批評しないことに合わせ、
      LLM 呼び出し回数を元と一致させる。
    - 批評の構造化出力が JSON として壊れていたら、安全側(= 元実装の無条件
      改訂に相当)に倒して応答全文を 1 批評として "revise" を返す。ループは
      max_rounds で必ず止まるため発散しない。
    - "revise" なのに批評が空なら改訂プロンプトに載せるものがないため
      "accept" に正規化する。
    """

    def __init__(self, agents: CritiqueLoopAgents) -> None:
        super().__init__(id="critic")
        self._agents = agents

    @handler
    async def critique(
        self, state: LoopState, ctx: WorkflowContext[CritiqueOutcome, CritiqueDecided]
    ) -> None:
        round_number = len(state.revisions) + 1
        if state.exhausted():
            await ctx.yield_output(
                CritiqueDecided(round=round_number, verdict=STOP_MAX_ROUNDS, critique_count=0)
            )
            await ctx.send_message(CritiqueOutcome(state=state, verdict=STOP_MAX_ROUNDS))
            return

        response = await self._agents.critic.run(critique_prompt(state.prompt, state.draft))
        try:
            parsed = parse_structured(response, CritiqueVerdict)
            verdict, critiques = parsed.verdict, list(parsed.critiques)
        except SchemaError:
            # 元実装の「批評は常に改訂につながる」に相当する安全側フォールバック
            verdict, critiques = "revise", [response.text]
        if verdict == "revise" and not critiques:
            verdict = "accept"

        await ctx.yield_output(
            CritiqueDecided(round=round_number, verdict=verdict, critique_count=len(critiques))
        )
        await ctx.send_message(CritiqueOutcome(state=state, verdict=verdict, critiques=critiques))


class ReviseExecutor(Executor):
    """批評を反映した改訂(元の revise_answer)。改訂後の状態をループエッジで
    critic へ戻す。"""

    def __init__(self, agents: CritiqueLoopAgents) -> None:
        super().__init__(id="revise")
        self._agents = agents

    @handler
    async def revise(
        self, outcome: CritiqueOutcome, ctx: WorkflowContext[LoopState, RevisionDone]
    ) -> None:
        state = outcome.state
        round_number = len(state.revisions) + 1
        response = await self._agents.reviser.run(
            revision_prompt(state.prompt, state.draft, outcome.critiques)
        )
        revised = response.text
        await ctx.yield_output(RevisionDone(round=round_number, chars=len(revised)))
        await ctx.send_message(
            LoopState(
                prompt=state.prompt,
                draft=revised,
                initial_draft=state.initial_draft,
                candidates=state.candidates,
                revisions=[
                    *state.revisions,
                    Revision(round=round_number, critiques=list(outcome.critiques), answer=revised),
                ],
                max_rounds=state.max_rounds,
            )
        )


class FinalizeExecutor(Executor):
    """終了した状態を最終成果物に詰め替える(元の results 組み立て)。"""

    def __init__(self) -> None:
        super().__init__(id="finalize")

    @handler
    async def finalize(
        self, outcome: CritiqueOutcome, ctx: WorkflowContext[Never, CritiqueLoopResult]
    ) -> None:
        state = outcome.state
        await ctx.yield_output(
            CritiqueLoopResult(
                prompt=state.prompt,
                final_answer=state.draft,
                initial_answer=state.initial_draft,
                candidates=state.candidates,
                revisions=state.revisions,
                stop_reason=STOP_ACCEPTED if outcome.verdict == "accept" else STOP_MAX_ROUNDS,
                max_rounds=state.max_rounds,
            )
        )


# --- 組み立て ---------------------------------------------------------------


def build_critique_loop_workflow(agents: CritiqueLoopAgents, max_rounds: int = DEFAULT_MAX_ROUNDS):
    """``await workflow.run(prompt)`` で実行するサイクリックワークフローを
    組み立てる。進捗は ``workflow.run(prompt, stream=True)`` の intermediate
    イベント(CandidateDone / DraftSynthesized / CritiqueDecided /
    RevisionDone)。"""
    if not agents.candidates:
        raise ValueError("candidate が 0 体です")
    if not MIN_MAX_ROUNDS <= max_rounds <= MAX_MAX_ROUNDS:
        raise ValueError(
            f"max_rounds は {MIN_MAX_ROUNDS}〜{MAX_MAX_ROUNDS}"
            f"(元アプリのスライダー範囲): {max_rounds}"
        )

    dispatcher = DispatcherExecutor(max_rounds)
    candidates = [CandidateExecutor(c.name, c.agent) for c in agents.candidates]
    synthesize = SynthesizeExecutor(agents)
    critic = CriticExecutor(agents)
    revise = ReviseExecutor(agents)
    finalize = FinalizeExecutor()

    return (
        WorkflowBuilder(
            start_executor=dispatcher,
            output_from=[finalize],
            intermediate_output_from=[*candidates, synthesize, critic, revise],
        )
        .add_fan_out_edges(dispatcher, candidates)
        .add_fan_in_edges(candidates, synthesize)
        .add_edge(synthesize, critic)
        # 元の for ループの継続判定に対応: accept / 上限到達なら finalize、
        # それ以外(revise)は改訂へ
        .add_switch_case_edge_group(
            critic,
            [
                Case(
                    condition=lambda msg: isinstance(msg, CritiqueOutcome)
                    and msg.verdict != "revise",
                    target=finalize,
                ),
                Default(target=revise),
            ],
        )
        .add_edge(revise, critic)  # ループエッジ
        .build()
    )
