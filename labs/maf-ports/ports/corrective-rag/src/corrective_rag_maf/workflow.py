"""CRAG の補正フローを LangGraph StateGraph から MAF WorkflowBuilder へ写像する。

元アプリのグラフ(corrective_rag.py):

    retrieve → grade_documents ─(decide_to_generate)─┬─ "generate" ────────▶ generate → END
                                                     └─ "transform_query" ▶ transform_query
                                                            → web_search → generate → END

- 状態は ``GraphState = {"keys": Dict[str, any]}`` という無型 dict 1 個で、
  各ノードが question / documents / run_web_search / generation を出し入れ
  していた。移植では**エッジごとに型付きメッセージ**(Retrieval /
  GradeOutcome / RewriteOutcome / WebSearchOutcome)に分解する。
- 条件分岐 ``add_conditional_edges(grade, decide_to_generate, {...})`` は
  ``add_switch_case_edge_group``(Case / Default)に対応。分岐条件は
  ``run_web_search == "Yes"``(文字列フラグ)→ ``GradeOutcome.
  needs_web_search``(bool)に置換。
- **ループなし(重要)**: 元実装の補正パスは transform_query → web_search →
  generate の一方向で、再採点・再書換は存在しない(CRAG 論文にあるループは
  この実装では単発パスに簡略化されている)。移植も同じトポロジ(DAG)を
  保ち、書換・Web 検索は最大 1 回。唯一のリトライは Web 検索のトランス
  ポートレベル 3 試行(元 tenacity → search.search_with_retry)。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Never

from agent_framework import Case, Default, Executor, WorkflowBuilder, WorkflowContext, handler

from .agents import CorrectiveRagAgents
from .retrieval import RetrievedDocument, SupportsRetrieve
from .schemas import GradeScore, parse_structured
from .search import SearchHit, search_with_retry

#: Web 検索の取得件数(元アプリの TavilySearchResults(max_results=3))
WEB_SEARCH_MAX_RESULTS = 3

# --- 元アプリの PromptTemplate(原文)-------------------------------------


def grade_prompt(context: str, question: str) -> str:
    """grade_documents ノードの PromptTemplate 原文。"""
    return (
        "You are grading the relevance of a retrieved document to a user question.\n"
        'Return ONLY a JSON object with a "score" field that is either "yes" or "no".\n'
        "Do not include any other text or explanation.\n\n"
        f"Document: {context}\n"
        f"Question: {question}\n\n"
        "Rules:\n"
        "- Check for related keywords or semantic meaning\n"
        "- Use lenient grading to only filter clear mismatches\n"
        '- Return exactly like this example: {"score": "yes"} or {"score": "no"}'
    )


def transform_prompt(question: str) -> str:
    """transform_query ノードの PromptTemplate 原文。"""
    return (
        "Generate a search-optimized version of this question by \n"
        "analyzing its core semantic meaning and intent.\n"
        "\n ------- \n"
        f"{question}"
        "\n ------- \n"
        "Return only the improved question with no additional text:"
    )


def generate_prompt(context: str, question: str) -> str:
    """generate ノードの PromptTemplate 原文。"""
    return (
        "Based on the following context, please answer the question.\n"
        f"Context: {context}\n"
        f"Question: {question}\n"
        "Answer:"
    )


# --- グラフを流れるメッセージ(元の GraphState["keys"] を型付きに分解)----


@dataclass
class DocumentGrade:
    """採点結果 1 件(観測・評価用。元アプリでは print ログのみだった)。"""

    source: str
    score: str  # "yes" | "no" | "error-kept"
    preview: str = ""


@dataclass
class Retrieval:
    """retrieve → grade_documents。"""

    question: str
    documents: list[RetrievedDocument]


@dataclass
class GradeOutcome:
    """grade_documents → 分岐(generate / transform_query)。

    ``documents`` は関連と採点された文書のみ(元の filtered_docs)。
    ``needs_web_search`` は元の ``run_web_search == "Yes"`` に対応。
    """

    question: str
    documents: list[RetrievedDocument]
    grades: list[DocumentGrade] = field(default_factory=list)
    needs_web_search: bool = False


@dataclass
class RewriteOutcome:
    """transform_query → web_search。question は書換後(元実装は state の
    question を書換後の better_question で上書きしていた)。"""

    question: str
    original_question: str
    documents: list[RetrievedDocument]
    grades: list[DocumentGrade] = field(default_factory=list)


@dataclass
class WebSearchOutcome:
    """web_search → generate。"""

    question: str
    original_question: str
    documents: list[RetrievedDocument]
    grades: list[DocumentGrade] = field(default_factory=list)
    web_result_count: int = 0
    web_search_failed: bool = False


# --- 進捗イベント(元アプリの Streamlit expander / print ログ相当)---------


@dataclass
class DocsRetrieved:
    count: int


@dataclass
class GradeDecided:
    """decide_to_generate の判断(元の "decision: generate/transform query")。"""

    kept: int
    dropped: int
    run_web_search: bool


@dataclass
class QueryRewritten:
    original: str
    rewritten: str


@dataclass
class WebSearched:
    result_count: int
    failed: bool


@dataclass
class CorrectiveRagResult:
    """最終成果物(元の state["keys"]["generation"] +実行の顛末)。"""

    question: str  # 生成に使った質問(補正パスでは書換後)
    original_question: str
    answer: str
    corrected: bool  # 補正パス(書換+Web 検索)を通ったか
    documents: list[RetrievedDocument]
    grades: list[DocumentGrade]
    web_result_count: int | None = None  # 直行パスでは None
    web_search_failed: bool = False

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


# --- Executors(元のノード関数に対応)-------------------------------------


class RetrieveExecutor(Executor):
    """ベクトル検索(元の retrieve ノード)。retriever は protocol 注入。"""

    def __init__(self, retriever: SupportsRetrieve) -> None:
        super().__init__(id="retrieve")
        self._retriever = retriever

    @handler
    async def retrieve(
        self, question: str, ctx: WorkflowContext[Retrieval, DocsRetrieved]
    ) -> None:
        documents = await self._retriever.retrieve(question)
        await ctx.yield_output(DocsRetrieved(count=len(documents)))
        await ctx.send_message(Retrieval(question=question, documents=documents))


class GradeExecutor(Executor):
    """文書ごとの関連度採点(元の grade_documents ノード)。

    元実装と同じく: yes → 残す / no → 落として Web 検索フラグを立てる /
    採点エラー → 安全側に倒して残す。文書 0 件のときはフラグが立たず
    直行 generate になる(元実装の暗黙挙動を踏襲。README の quirk 参照)。
    """

    def __init__(self, agents: CorrectiveRagAgents) -> None:
        super().__init__(id="grade_documents")
        self._agents = agents

    @handler
    async def grade(
        self, retrieval: Retrieval, ctx: WorkflowContext[GradeOutcome, GradeDecided]
    ) -> None:
        filtered: list[RetrievedDocument] = []
        grades: list[DocumentGrade] = []
        needs_web_search = False

        for doc in retrieval.documents:
            preview = doc.content[:80]
            try:
                response = await self._agents.grader.run(
                    grade_prompt(doc.content, retrieval.question)
                )
                score = parse_structured(response, GradeScore)
                if score.score == "yes":
                    filtered.append(doc)
                    grades.append(DocumentGrade(source=doc.source, score="yes", preview=preview))
                else:
                    needs_web_search = True
                    grades.append(DocumentGrade(source=doc.source, score="no", preview=preview))
            except Exception:  # noqa: BLE001
                # 元実装の "On error, keep the document to be safe" を踏襲
                filtered.append(doc)
                grades.append(DocumentGrade(source=doc.source, score="error-kept", preview=preview))

        await ctx.yield_output(
            GradeDecided(
                kept=len(filtered),
                dropped=len(retrieval.documents) - len(filtered),
                run_web_search=needs_web_search,
            )
        )
        await ctx.send_message(
            GradeOutcome(
                question=retrieval.question,
                documents=filtered,
                grades=grades,
                needs_web_search=needs_web_search,
            )
        )


class TransformQueryExecutor(Executor):
    """検索最適化クエリへの書換(元の transform_query ノード)。"""

    def __init__(self, agents: CorrectiveRagAgents) -> None:
        super().__init__(id="transform_query")
        self._agents = agents

    @handler
    async def transform(
        self, outcome: GradeOutcome, ctx: WorkflowContext[RewriteOutcome, QueryRewritten]
    ) -> None:
        response = await self._agents.rewriter.run(transform_prompt(outcome.question))
        better_question = response.text.strip() or outcome.question
        await ctx.yield_output(
            QueryRewritten(original=outcome.question, rewritten=better_question)
        )
        await ctx.send_message(
            RewriteOutcome(
                question=better_question,
                original_question=outcome.question,
                documents=outcome.documents,
                grades=outcome.grades,
            )
        )


class WebSearchExecutor(Executor):
    """Web 検索フォールバック(元の web_search ノード。Tavily → 自前 DDG)。

    元実装と同じく: 3 試行のリトライ(search.search_with_retry)で失敗、
    または結果 0 件なら、文書リストを変えずに generate へ進む。成功時は
    結果を 1 文書に束ねて追加する(元の Document(page_content="Title/Content
    の連結", metadata={"source": "tavily_search", ...}) に対応)。
    """

    def __init__(
        self,
        web_search: Callable[[str], Awaitable[list[SearchHit]]],
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        super().__init__(id="web_search")
        self._web_search = web_search
        self._sleep = sleep

    @handler
    async def search(
        self, outcome: RewriteOutcome, ctx: WorkflowContext[WebSearchOutcome, WebSearched]
    ) -> None:
        documents = list(outcome.documents)
        hits: list[SearchHit] = []
        failed = False
        try:
            hits = await search_with_retry(self._web_search, outcome.question, sleep=self._sleep)
        except Exception:  # noqa: BLE001
            # 元実装の "Search failed after retries" — 文書を変えずに続行
            failed = True

        if hits:
            # 元実装と同じ形("Title: ...\nContent: ..." を空行連結した 1 文書)
            web_results = [f"Title: {hit.title}\nContent: {hit.snippet}\n" for hit in hits]
            documents.append(
                RetrievedDocument(
                    content="\n\n".join(web_results),
                    source="web_search",
                    title=f"Web search results for: {outcome.question}",
                )
            )

        await ctx.yield_output(WebSearched(result_count=len(hits), failed=failed))
        await ctx.send_message(
            WebSearchOutcome(
                question=outcome.question,
                original_question=outcome.original_question,
                documents=documents,
                grades=outcome.grades,
                web_result_count=len(hits),
                web_search_failed=failed,
            )
        )


class GenerateExecutor(Executor):
    """回答生成(元の generate ノード)。

    2 つの handler を持ち、直行(GradeOutcome)と補正パス経由
    (WebSearchOutcome)のどちらの経路でも受けられる。web_search → generate
    のエッジは無条件(再採点なし)なのは元実装と同じ。
    """

    def __init__(self, agents: CorrectiveRagAgents) -> None:
        super().__init__(id="generate")
        self._agents = agents

    @handler
    async def generate_direct(
        self, outcome: GradeOutcome, ctx: WorkflowContext[Never, CorrectiveRagResult]
    ) -> None:
        answer = await self._answer(outcome.documents, outcome.question)
        await ctx.yield_output(
            CorrectiveRagResult(
                question=outcome.question,
                original_question=outcome.question,
                answer=answer,
                corrected=False,
                documents=outcome.documents,
                grades=outcome.grades,
            )
        )

    @handler
    async def generate_corrected(
        self, outcome: WebSearchOutcome, ctx: WorkflowContext[Never, CorrectiveRagResult]
    ) -> None:
        answer = await self._answer(outcome.documents, outcome.question)
        await ctx.yield_output(
            CorrectiveRagResult(
                question=outcome.question,
                original_question=outcome.original_question,
                answer=answer,
                corrected=True,
                documents=outcome.documents,
                grades=outcome.grades,
                web_result_count=outcome.web_result_count,
                web_search_failed=outcome.web_search_failed,
            )
        )

    async def _answer(self, documents: list[RetrievedDocument], question: str) -> str:
        # 元実装: context = "\n\n".join(doc.page_content)(文書 0 件なら空)
        context = "\n\n".join(doc.content for doc in documents)
        response = await self._agents.generator.run(generate_prompt(context, question))
        return response.text


# --- 組み立て(元の StateGraph 構築部に対応)------------------------------


def build_corrective_rag_workflow(
    agents: CorrectiveRagAgents,
    retriever: SupportsRetrieve,
    web_search: Callable[[str], Awaitable[list[SearchHit]]],
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
):
    """``await workflow.run(question)`` で実行する単発ワークフローを組み立てる。
    進捗は ``workflow.run(question, stream=True)`` の intermediate イベント
    (DocsRetrieved / GradeDecided / QueryRewritten / WebSearched)。"""
    retrieve = RetrieveExecutor(retriever)
    grade = GradeExecutor(agents)
    transform = TransformQueryExecutor(agents)
    search = WebSearchExecutor(web_search, sleep=sleep)
    generate = GenerateExecutor(agents)

    return (
        WorkflowBuilder(
            start_executor=retrieve,
            output_from=[generate],
            intermediate_output_from=[retrieve, grade, transform, search],
        )
        .add_edge(retrieve, grade)
        # 元の add_conditional_edges(grade, decide_to_generate, {...}) に対応
        .add_switch_case_edge_group(
            grade,
            [
                Case(
                    condition=lambda outcome: getattr(outcome, "needs_web_search", False),
                    target=transform,
                ),
                Default(target=generate),
            ],
        )
        .add_edge(transform, search)
        .add_edge(search, generate)
        .build()
    )
