"""ワークフローのオフラインテスト。LLM・ベクトル検索・Web 検索はすべて
scripted fake(ネットワーク不要)。パターンは ports/research-handoff/tests/
test_workflow.py の ScriptedAgent / Harness を踏襲。

検証項目(Port 4 の要点):
- 採点分岐: 全文書「高関連」→ 直接 generate / 低関連あり → 書換 →
  Web 検索 → generate(元の decide_to_generate の両分岐)
- ループ上限: 元実装は補正パスを最大 1 回しか通らない DAG(再採点・再書換
  なし)。書換/Web 検索/生成の呼び出し回数で固定する。Web 検索の
  トランスポートリトライも元の 3 試行で打ち切り。
- 各ノードが受け取るコンテキスト(採点プロンプト・書換プロンプト・生成
  コンテキストの内容)
- 採点の解釈: ネイティブ .value / JSON 抽出 / パース不能 → 安全側に文書を残す
- Web 検索の失敗・0 件時: 文書リストを変えずに生成へ進む(元実装の挙動)
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

pytest.importorskip("agent_framework")

from corrective_rag_maf.agents import CorrectiveRagAgents
from corrective_rag_maf.retrieval import RetrievedDocument
from corrective_rag_maf.schemas import GradeScore
from corrective_rag_maf.search import SearchHit
from corrective_rag_maf.workflow import (
    CorrectiveRagResult,
    DocsRetrieved,
    GradeDecided,
    QueryRewritten,
    WebSearched,
    build_corrective_rag_workflow,
)

QUESTION = "What are the limits of the Azure AI Search free tier?"

YES = json.dumps({"score": "yes"})
NO = json.dumps({"score": "no"})

DOC_RELEVANT = RetrievedDocument(
    content="Free tier allows 3 indexes and 50MB of storage; no semantic ranker.",
    source="azure-ai-search-vector-tiers.md",
    title="Azure AI Search tiers",
    score=0.9,
)
DOC_IRRELEVANT = RetrievedDocument(
    content="Code Interpreter runs Python in a sandbox with per-session billing.",
    source="foundry-agent-service.md",
    title="Agent Service",
    score=0.4,
)


@dataclass
class FakeResponse:
    text: str
    value: Any = None


class ScriptedAgent:
    """受け取ったメッセージを記録し、決められた応答を順に返す
    (応答リストが尽きたら最後のものを繰り返す)。"""

    def __init__(self, replies: Sequence[str] = ("",), values: Sequence[Any] = ()) -> None:
        self.replies = list(replies)
        self.values = list(values)
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        index = min(len(self.received), len(self.replies) - 1)
        self.received.append(message)
        value = self.values[index] if index < len(self.values) else None
        return FakeResponse(text=self.replies[index], value=value)


class FakeRetriever:
    def __init__(self, documents: list[RetrievedDocument]) -> None:
        self.documents = documents
        self.questions: list[str] = []

    async def retrieve(self, question: str) -> list[RetrievedDocument]:
        self.questions.append(question)
        return list(self.documents)


class FakeWebSearch:
    def __init__(
        self, hits: list[SearchHit] | None = None, error: Exception | None = None
    ) -> None:
        self.hits = hits or []
        self.error = error
        self.queries: list[str] = []

    async def __call__(self, query: str) -> list[SearchHit]:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return list(self.hits)


async def no_sleep(seconds: float) -> None:
    return None


@dataclass
class Harness:
    grader: ScriptedAgent
    rewriter: ScriptedAgent
    generator: ScriptedAgent
    retriever: FakeRetriever
    web: FakeWebSearch
    results: list[CorrectiveRagResult] = field(default_factory=list)
    events: list[Any] = field(default_factory=list)
    sleeps: list[float] = field(default_factory=list)

    async def run(self, question: str = QUESTION) -> CorrectiveRagResult:
        async def record_sleep(seconds: float) -> None:
            self.sleeps.append(seconds)

        workflow = build_corrective_rag_workflow(
            CorrectiveRagAgents(
                grader=self.grader, rewriter=self.rewriter, generator=self.generator
            ),
            self.retriever,
            self.web,
            sleep=record_sleep,
        )
        async for event in workflow.run(question, stream=True):
            if event.type == "intermediate":
                self.events.append(event.data)
            elif event.type == "output":
                self.results.append(event.data)
        assert len(self.results) == 1, "最終出力はちょうど 1 回であるべき"
        return self.results[0]


def make_harness(
    documents: list[RetrievedDocument] | None = None,
    grader_replies: Sequence[str] = (YES, YES),
    grader_values: Sequence[Any] = (),
    rewriter_reply: str = "Azure AI Search free tier limits indexes storage",
    generator_reply: str = "The free tier allows 3 indexes and 50MB of storage.",
    web_hits: list[SearchHit] | None = None,
    web_error: Exception | None = None,
) -> Harness:
    if documents is None:
        documents = [DOC_RELEVANT, DOC_IRRELEVANT]
    if web_hits is None:
        web_hits = [
            SearchHit(
                title="Azure AI Search pricing",
                url="https://example.com/pricing",
                snippet="Free tier: 3 indexes, 50 MB, no SLA.",
            )
        ]
    return Harness(
        grader=ScriptedAgent(grader_replies, values=grader_values),
        rewriter=ScriptedAgent([rewriter_reply]),
        generator=ScriptedAgent([generator_reply]),
        retriever=FakeRetriever(documents),
        web=FakeWebSearch(hits=web_hits, error=web_error),
    )


# --- 採点分岐: 高関連 → 直接 generate --------------------------------------


async def test_all_relevant_generates_directly() -> None:
    h = make_harness(grader_replies=(YES, YES))
    result = await h.run()

    assert result.corrected is False
    assert result.question == result.original_question == QUESTION
    assert result.web_result_count is None
    assert [g.score for g in result.grades] == ["yes", "yes"]

    # 補正パスは一切通らない
    assert h.rewriter.received == []
    assert h.web.queries == []
    # 文書は 1 件ずつ採点される(元の for d in documents ループ)
    assert len(h.grader.received) == 2
    assert len(h.generator.received) == 1


async def test_direct_generate_prompt_carries_context_and_question() -> None:
    h = make_harness(grader_replies=(YES, YES))
    await h.run()

    prompt = h.generator.received[0]
    assert "Based on the following context, please answer the question." in prompt
    assert DOC_RELEVANT.content in prompt
    assert DOC_IRRELEVANT.content in prompt  # yes 採点なので残る
    assert QUESTION in prompt


async def test_grade_prompt_carries_document_and_question() -> None:
    h = make_harness()
    await h.run()

    prompt = h.grader.received[0]
    assert DOC_RELEVANT.content in prompt
    assert QUESTION in prompt
    assert 'Return ONLY a JSON object with a "score" field' in prompt


# --- 採点分岐: 低関連 → 書換 → Web 検索 → generate --------------------------


async def test_low_relevance_triggers_rewrite_and_web_search() -> None:
    h = make_harness(grader_replies=(YES, NO))
    result = await h.run()

    assert result.corrected is True
    assert result.original_question == QUESTION
    assert result.question == "Azure AI Search free tier limits indexes storage"
    assert [g.score for g in result.grades] == ["yes", "no"]
    assert result.web_result_count == 1

    # 書換プロンプトは元の transform_query の原文形で、元クエリを含む
    assert len(h.rewriter.received) == 1
    assert "search-optimized version" in h.rewriter.received[0]
    assert QUESTION in h.rewriter.received[0]

    # Web 検索は書換後のクエリで実行される(元実装は state の question を上書き)
    assert h.web.queries == ["Azure AI Search free tier limits indexes storage"]


async def test_corrected_generate_prompt_has_filtered_docs_and_web_results() -> None:
    h = make_harness(grader_replies=(YES, NO))
    result = await h.run()

    prompt = h.generator.received[0]
    assert DOC_RELEVANT.content in prompt  # yes 採点は残る
    assert DOC_IRRELEVANT.content not in prompt  # no 採点は落ちる
    # Web 結果は元実装と同じ "Title: ...\nContent: ..." 形の 1 文書に束ねられる
    assert "Title: Azure AI Search pricing" in prompt
    assert "Content: Free tier: 3 indexes, 50 MB, no SLA." in prompt
    # 生成には書換後の質問を使う
    assert "Azure AI Search free tier limits indexes storage" in prompt

    web_docs = [d for d in result.documents if d.source == "web_search"]
    assert len(web_docs) == 1


async def test_all_documents_dropped_still_generates_from_web_only() -> None:
    h = make_harness(grader_replies=(NO, NO))
    result = await h.run()

    assert result.corrected is True
    assert [g.score for g in result.grades] == ["no", "no"]
    prompt = h.generator.received[0]
    assert DOC_RELEVANT.content not in prompt
    assert DOC_IRRELEVANT.content not in prompt
    assert "Title: Azure AI Search pricing" in prompt
    assert [d.source for d in result.documents] == ["web_search"]


# --- 元実装の quirk と安全側の挙動 -----------------------------------------


async def test_empty_retrieval_goes_direct_with_empty_context() -> None:
    """元実装の quirk: 文書 0 件では run_web_search フラグが立たず、空
    コンテキストのまま直接 generate される(retriever=None のときの挙動)。"""
    h = make_harness(documents=[])
    result = await h.run()

    assert result.corrected is False
    assert h.grader.received == []
    assert h.rewriter.received == []
    assert h.web.queries == []
    prompt = h.generator.received[0]
    assert "Context: \n" in prompt  # 空コンテキスト


async def test_unparseable_grade_keeps_document() -> None:
    """元実装の "On error, keep the document to be safe" の踏襲。"""
    h = make_harness(grader_replies=("the doc looks fine to me", YES))
    result = await h.run()

    assert result.corrected is False  # エラー採点は Web 検索フラグを立てない
    assert [g.score for g in result.grades] == ["error-kept", "yes"]
    assert DOC_RELEVANT.content in h.generator.received[0]


async def test_grader_native_value_path() -> None:
    """ネイティブ構造化出力(.value が GradeScore)を優先して使う。"""
    h = make_harness(
        grader_replies=("(not json)", "(not json)"),
        grader_values=(GradeScore(score="yes"), GradeScore(score="no")),
    )
    result = await h.run()

    assert [g.score for g in result.grades] == ["yes", "no"]
    assert result.corrected is True


# --- Web 検索の失敗・0 件(元実装: 文書を変えずに続行)---------------------


async def test_web_search_failure_still_generates_with_filtered_docs() -> None:
    h = make_harness(grader_replies=(YES, NO), web_error=RuntimeError("ddg down"))
    result = await h.run()

    assert result.corrected is True
    assert result.web_search_failed is True
    assert result.web_result_count == 0
    # リトライは元実装と同じ 3 試行+指数待ち(4s, 8s)で打ち切り
    assert len(h.web.queries) == 3
    assert h.sleeps == [4.0, 8.0]
    # 文書リストは変わらず、残った文書だけで生成される
    assert [d.source for d in result.documents] == [DOC_RELEVANT.source]
    assert len(h.generator.received) == 1


async def test_web_search_empty_results_appends_nothing() -> None:
    h = make_harness(grader_replies=(NO, NO), web_hits=[])
    result = await h.run()

    assert result.web_search_failed is False
    assert result.web_result_count == 0
    assert result.documents == []  # 全文書 drop + Web 0 件 → 空コンテキスト生成


# --- ループ上限(元実装は補正パス最大 1 回の DAG)---------------------------


async def test_single_corrective_pass_no_regrade_or_rerewrite() -> None:
    """web_search → generate のエッジは無条件: Web 結果は再採点されず、
    書換も 1 回きり(元実装のグラフと同じ)。無限ループは構造的に起きない。"""
    h = make_harness(grader_replies=(NO, NO))
    await h.run()

    assert len(h.grader.received) == 2  # 初回検索の文書数と同じ(再採点なし)
    assert len(h.rewriter.received) == 1  # 再書換なし
    assert len(h.web.queries) == 1  # 成功時は 1 回
    assert len(h.generator.received) == 1  # 生成は 1 回


# --- 進捗イベントと実行 API -------------------------------------------------


async def test_progress_events_direct_route() -> None:
    h = make_harness(grader_replies=(YES, YES))
    await h.run()

    assert [type(e).__name__ for e in h.events] == ["DocsRetrieved", "GradeDecided"]
    retrieved, decided = h.events
    assert retrieved == DocsRetrieved(count=2)
    assert decided == GradeDecided(kept=2, dropped=0, run_web_search=False)


async def test_progress_events_corrective_route() -> None:
    h = make_harness(grader_replies=(YES, NO))
    await h.run()

    assert [type(e).__name__ for e in h.events] == [
        "DocsRetrieved",
        "GradeDecided",
        "QueryRewritten",
        "WebSearched",
    ]
    decided = h.events[1]
    assert decided == GradeDecided(kept=1, dropped=1, run_web_search=True)
    rewritten = h.events[2]
    assert isinstance(rewritten, QueryRewritten)
    assert rewritten.original == QUESTION
    assert h.events[3] == WebSearched(result_count=1, failed=False)


async def test_run_without_stream_returns_output() -> None:
    h = make_harness()
    workflow = build_corrective_rag_workflow(
        CorrectiveRagAgents(grader=h.grader, rewriter=h.rewriter, generator=h.generator),
        h.retriever,
        h.web,
        sleep=no_sleep,
    )
    result = await workflow.run(QUESTION)
    outputs = result.get_outputs() if hasattr(result, "get_outputs") else result
    # API 差異に耐える: 何らかの形で CorrectiveRagResult が取れること
    if isinstance(outputs, list):
        assert any(isinstance(o, CorrectiveRagResult) for o in outputs)
    else:
        assert isinstance(outputs, CorrectiveRagResult)


async def test_result_to_dict_is_json_serializable() -> None:
    h = make_harness(grader_replies=(YES, NO))
    result = await h.run()

    payload = json.dumps(result.to_dict(), ensure_ascii=False)
    parsed = json.loads(payload)
    assert parsed["corrected"] is True
    assert parsed["original_question"] == QUESTION
    assert parsed["grades"][1]["score"] == "no"
    assert parsed["documents"][-1]["source"] == "web_search"
