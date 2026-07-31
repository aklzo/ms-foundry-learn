"""ライブスモーク(実 Foundry + 実 Code Interpreter コンテナ)。既定では
除外され、``uv run pytest -m live`` で実行する。要 labs/maf-ports/.env。

**課金注意**: このテストは code_interpreter コンテナを起動する。Code
Interpreter はセッション単位の追加課金(アクティブ 1 時間/アイドル 30 分 —
docs/survey/features/04-tools-knowledge.md)。

確認項目(PORTING.md §4):
1. サンプル CSV が Files API にアップロードでき、code_interpreter コンテナの
   file_ids として渡ること
2. 実モデルがサンドボックスで pandas を実行し、「合計と上位カテゴリ」の
   **正しい数値**(total 3,225,050 / Electronics)が応答に含まれること
3. トレースが App Insights に届くこと(このテストでは送信の有効化まで。
   到達確認は CLI 実行後に az monitor app-insights query で行う)
"""

from pathlib import Path

import pytest

from data_analysis_ci_maf.config import ConfigError, FoundrySettings

pytestmark = pytest.mark.live

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample_sales.csv"

#: tests/test_datafile.py::test_sample_csv_shape_and_totals で固定した正解値
EXPECTED_TOTAL = 3225050
EXPECTED_TOP_CATEGORY = "Electronics"


@pytest.fixture(scope="module")
def settings() -> FoundrySettings:
    try:
        return FoundrySettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def test_code_interpreter_analysis_live(settings: FoundrySettings) -> None:
    from data_analysis_ci_maf.agents import build_analyst_agent, build_chat_client
    from data_analysis_ci_maf.analysis import build_analysis_prompt, run_analysis
    from data_analysis_ci_maf.datafile import upload_data_file, validate_data_file
    from data_analysis_ci_maf.observability import setup_tracing
    from data_analysis_ci_maf.tools import build_code_interpreter_tool

    setup_tracing(settings.app_insights_connection_string)

    data_path = validate_data_file(SAMPLE_CSV)
    chat_client = build_chat_client(settings)
    file_id = await upload_data_file(chat_client.client.files, data_path)
    assert file_id

    tool = build_code_interpreter_tool(chat_client, [file_id])
    agent = build_analyst_agent(chat_client, tool)
    prompt = build_analysis_prompt(
        "What is the total revenue, and which category has the highest revenue? "
        "Give exact numbers.",
        data_path.name,
    )

    result = await run_analysis(agent, prompt)

    answer = result.text
    assert answer.strip()
    # 数値は桁区切りの揺れを吸収して照合する
    normalized = answer.replace(",", "").replace(" ", "")
    assert str(EXPECTED_TOTAL) in normalized, f"合計 {EXPECTED_TOTAL} が応答にない: {answer}"
    assert EXPECTED_TOP_CATEGORY.lower() in answer.lower()
    # サンドボックスで実際にコードが実行されたこと(抽出ロジックの実地確認)
    assert result.code_blocks, "code_interpreter の実行コードが応答に含まれていない"
