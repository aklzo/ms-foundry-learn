"""ライブスモーク(実 Foundry + 実 Azure AI Search)。既定では除外され、
``uv run pytest -m live`` で実行する。要 labs/maf-ports/.env(AZURE_SEARCH_*
は ports/corrective-rag/infra/main.bicep の出力)。

**前提: インデックスが存在すること。** 事前に 1 回だけ実行しておく:

    uv sync --extra live
    uv run python scripts/setup_index.py

(data/*.md を text-embedding-3-small で埋め込み、corrective-rag インデックス
を作成+投入する。インデックス未作成のままだと SearchClient が 404 を返す。)

確認項目(PORTING.md §4):
1. 実モデル+実インデックスで 1 シナリオ(retrieve → grade → generate、
   低関連なら書換+Web 検索経由)が正常完走すること
2. トレースが App Insights に届くこと(このテストでは送信の有効化まで。
   到達確認は CLI 実行後に az monitor app-insights query で行う)
"""

import pytest

from corrective_rag_maf.config import ConfigError, CorrectiveRagSettings

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def settings() -> CorrectiveRagSettings:
    try:
        return CorrectiveRagSettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def test_full_workflow_live(settings: CorrectiveRagSettings) -> None:
    from corrective_rag_maf.agents import build_agents, build_chat_client
    from corrective_rag_maf.observability import setup_tracing
    from corrective_rag_maf.retrieval import make_azure_search_retriever
    from corrective_rag_maf.search import ddg_search, default_http_client
    from corrective_rag_maf.workflow import (
        WEB_SEARCH_MAX_RESULTS,
        CorrectiveRagResult,
        DocsRetrieved,
        build_corrective_rag_workflow,
    )

    setup_tracing(settings.app_insights_connection_string)
    http = default_http_client()
    retriever, adapter = make_azure_search_retriever(settings)

    async def web_search(query: str):
        return await ddg_search(http, query, WEB_SEARCH_MAX_RESULTS)

    try:
        agents = build_agents(build_chat_client(settings))
        workflow = build_corrective_rag_workflow(agents, retriever, web_search)

        result = None
        retrieved: list[DocsRetrieved] = []
        async for event in workflow.run(
            # 同梱コーパス(data/*.md)で答えられる質問 → 直行 generate が期待値
            "Azure AI Search の Free レベルにはどんな制約がありますか?",
            stream=True,
        ):
            if event.type == "intermediate" and isinstance(event.data, DocsRetrieved):
                retrieved.append(event.data)
            elif event.type == "output":
                result = event.data
    finally:
        await adapter.aclose()
        await http.aclose()

    assert isinstance(result, CorrectiveRagResult)
    assert retrieved and retrieved[0].count > 0, (
        "検索結果 0 件 — インデックス未投入の可能性(scripts/setup_index.py を実行)"
    )
    assert result.answer.strip()
    assert len(result.answer) > 50
    # 直行・補正どちらの経路でも grades は初回取得文書の数だけ付く
    assert len(result.grades) == retrieved[0].count
