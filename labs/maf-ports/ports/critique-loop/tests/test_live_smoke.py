"""ライブスモーク(実 Foundry エンドポイント)。既定では除外され、
``uv run pytest -m live`` で実行する。要 labs/maf-ports/.env。

確認項目(PORTING.md §4):
1. 並列候補 3 → 統合 → 批評(構造化出力)→(必要なら)改訂、が実モデルで
   完走し、最終回答が返ること
2. 批評の verdict / critiques が構造化出力として取れていること
3. トレースが App Insights に届くこと(このテストでは送信の有効化まで。
   到達確認は CLI 実行後に az monitor app-insights query で行う)

クラウド評価(scripts/run_cloud_eval.py)はこのテストに含めない — 評価ラン
は非同期のサーバー側ジョブで、手順として README に記載(実行は呼び出し元)。
"""

import pytest

from critique_loop_maf.config import ConfigError, FoundrySettings

pytestmark = pytest.mark.live

PROMPT = "Explain the concept of recursion with examples."


@pytest.fixture(scope="module")
def settings() -> FoundrySettings:
    try:
        return FoundrySettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def test_critique_loop_live(settings: FoundrySettings) -> None:
    from critique_loop_maf.agents import build_agents, build_chat_client
    from critique_loop_maf.observability import setup_tracing
    from critique_loop_maf.workflow import (
        CritiqueDecided,
        CritiqueLoopResult,
        build_critique_loop_workflow,
    )

    setup_tracing(settings.app_insights_connection_string)

    agents = build_agents(build_chat_client(settings))
    # max_rounds=1: 最小の 1 周(批評→改訂 or 早期終了)でコストを抑える
    workflow = build_critique_loop_workflow(agents, max_rounds=1)

    result: CritiqueLoopResult | None = None
    critiques: list[CritiqueDecided] = []
    async for event in workflow.run(PROMPT, stream=True):
        if event.type == "intermediate" and isinstance(event.data, CritiqueDecided):
            critiques.append(event.data)
        elif event.type == "output":
            result = event.data

    assert isinstance(result, CritiqueLoopResult)
    assert result.final_answer.strip()
    assert result.initial_answer.strip()
    assert len(result.candidates) == 3
    assert len(result.revisions) <= 1
    assert result.stop_reason in ("accepted", "max-rounds")
    # 批評の構造化出力が動いたこと(最初の判断は LLM 由来)
    assert critiques
    assert critiques[0].verdict in ("accept", "revise")
    if result.revisions:
        # 改訂があったなら批評が改訂プロンプト経由で反映されている
        assert result.revisions[0].critiques
        assert result.final_answer != result.initial_answer
