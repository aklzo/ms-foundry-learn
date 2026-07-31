"""デプロイ zip ステージングと Routine ペイロード(純関数)のオフラインテスト。

hosted agent のコードデプロイ規約(zip ルートに main.py / requirements.txt)と
Routines プレビューの REST 契約(トリガー/アクションのスキーマ・フィーチャー
ヘッダー)をここで固定する — スクリプト側は HTTP/SDK を貼るだけ。
"""

import zipfile
from pathlib import Path

from hn_briefing_maf.hosting_setup import (
    RESPONSES_PROTOCOL_VERSION,
    create_code_zip,
    hosted_agent_definition_kwargs,
    stage_hosted_agent_dir,
)
from hn_briefing_maf.routine_setup import (
    DEFAULT_CRON,
    DEFAULT_TIME_ZONE,
    ROUTINES_FEATURE_HEADER,
    TOKEN_SCOPE,
    build_routine_payload,
    routine_url,
)

# --- hosted agent デプロイ(zip 規約+バージョン定義)---


def test_staged_zip_places_entrypoint_and_package_at_root(tmp_path: Path) -> None:
    """quickstart の Troubleshooting が要求する「zip ルートに main.py と
    requirements.txt」+ import 可能なパッケージ同梱を固定する。"""
    staged = stage_hosted_agent_dir(tmp_path / "staged")
    zip_path = create_code_zip(staged, tmp_path / "agent.zip")

    with zipfile.ZipFile(zip_path) as zip_file:
        names = set(zip_file.namelist())
    assert "main.py" in names
    assert "requirements.txt" in names
    assert "hn_briefing_maf/__init__.py" in names
    assert "hn_briefing_maf/hosted.py" in names
    assert not any("__pycache__" in name for name in names)
    # ホスティング層の付帯物(deploy スクリプト等)はコンテナに入れない
    assert "deploy_hosted_agent.py" not in names


def test_definition_kwargs_encode_container_protocol_2_and_keyless_env() -> None:
    kwargs = hosted_agent_definition_kwargs(
        project_endpoint="https://acct.services.ai.azure.com/api/projects/maf-ports",
        model="gpt-fake",
    )

    assert kwargs["entry_point"] == ["python", "main.py"]
    assert kwargs["protocols"] == [("responses", "2.0.0")]
    assert RESPONSES_PROTOCOL_VERSION == "2.0.0"  # 1.0.0 は非推奨(猶予後ブロック)
    assert (kwargs["cpu"], kwargs["memory"]) == ("0.5", "1Gi")
    # コンテナへ渡すのは接続先とモデル名のみ — API キーは渡さない(agent identity)
    assert kwargs["environment_variables"] == {
        "FOUNDRY_PROJECT_ENDPOINT": "https://acct.services.ai.azure.com/api/projects/maf-ports",
        "FOUNDRY_MODEL_NAME": "gpt-fake",
    }


# --- Routine(REST 契約)---


def test_routine_payload_matches_preview_rest_schema() -> None:
    payload = build_routine_payload(agent_name="hn-briefing-agent")

    trigger = payload["triggers"]["daily-briefing"]
    assert trigger == {
        "type": "schedule",
        "cron_expression": DEFAULT_CRON,
        "time_zone": DEFAULT_TIME_ZONE,
    }
    assert payload["action"]["type"] == "invoke_agent_responses_api"
    assert payload["action"]["agent_name"] == "hn-briefing-agent"
    assert "input" in payload["action"]
    assert payload["enabled"] is True
    assert len(payload["triggers"]) == 1  # プレビューは 1 トリガー+1 アクション


def test_routine_defaults_port_original_schedule() -> None:
    """元 README の推奨スケジュール(平日朝)を JST で踏襲。"""
    assert DEFAULT_CRON == "0 9 * * 1-5"
    assert DEFAULT_TIME_ZONE == "Asia/Tokyo"


def test_routine_url_and_headers() -> None:
    endpoint = "https://acct.services.ai.azure.com/api/projects/maf-ports/"
    # api-version クエリは必須(欠くと BadRequest — ライブで実測し追加)
    assert routine_url(endpoint, "hn-briefing-daily") == (
        "https://acct.services.ai.azure.com/api/projects/maf-ports/routines/hn-briefing-daily"
        "?api-version=v1"
    )
    assert routine_url(endpoint, "x", suffix=":dispatch_async").endswith(
        "/routines/x:dispatch_async?api-version=v1"
    )
    assert routine_url(endpoint, "x", suffix="/runs").endswith(
        "/routines/x/runs?api-version=v1"
    )
    # プレビューのフィーチャーヘッダーとトークンリソース(Learn の REST 例のまま)
    assert ROUTINES_FEATURE_HEADER == {"Foundry-Features": "Routines=V1Preview"}
    assert TOKEN_SCOPE == "https://ai.azure.com/.default"
