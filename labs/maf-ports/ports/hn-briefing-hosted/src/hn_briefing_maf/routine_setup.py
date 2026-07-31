"""Routines(プレビュー)のペイロード組み立て(純関数)。

REST を貼るのは scripts/setup_routine.py のみ。契約は Learn の
how-to/use-routines(2026-07 版)から:

- ``PUT {project_endpoint}/routines/{name}``(api-version クエリなし)
- 全リクエストに **``Foundry-Features: Routines=V1Preview``** ヘッダー必須
- Bearer トークンのリソースは ``https://ai.azure.com``
- trigger: ``{"type": "schedule", "cron_expression": ..., "time_zone": ...}``
  (cron_expression / time_zone は必須。**最小間隔 5 分**)
- action: ``{"type": "invoke_agent_responses_api", "agent_name": ..., "input": ...}``
- 操作系: POST ``:enable`` / ``:disable`` / ``:dispatch_async``(手動テスト
  実行の公開契約はこれのみ)、GET ``/runs``(実行履歴)

リージョン制約(実装前調査): Routines のプレビュー対応リージョンは
East US / East US 2 / West US / West US 2 / West Central US /
North Central US / Sweden Central / **Japan East** の 8 つ。
**共有基盤の Japan East は対応リージョンに含まれる**(README 参照)。
"""

from __future__ import annotations

from typing import Any

#: Routines プレビューの全リクエストに必須のフィーチャーヘッダー
ROUTINES_FEATURE_HEADER = {"Foundry-Features": "Routines=V1Preview"}

#: Bearer トークンのリソース(az account get-access-token --resource 相当)
TOKEN_SCOPE = "https://ai.azure.com/.default"

#: 既定のスケジュール: 平日 9:00 JST(元 README の推奨 `0 9 * * 1-5` を踏襲。
#: 元は Cloud Scheduler のタイムゾーン設定に相当するものを time_zone で指定)
DEFAULT_CRON = "0 9 * * 1-5"
DEFAULT_TIME_ZONE = "Asia/Tokyo"

#: ルーチンがエージェントに送る既定プロンプト
DEFAULT_INPUT = (
    "Give me today's AgentScout brief: the top 5 Hacker News stories for "
    "AI-agent builders, with why each matters and next actions."
)

DEFAULT_ROUTINE_NAME = "hn-briefing-daily"


ROUTINES_API_VERSION = "v1"


def routine_url(
    project_endpoint: str,
    routine_name: str,
    *,
    suffix: str = "",
    api_version: str = ROUTINES_API_VERSION,
) -> str:
    """ルーチンの REST URL(suffix は ``:dispatch_async`` / ``/runs`` 等)。

    api-version クエリは必須(欠くと BadRequest。ライブで実測)。
    """
    base = project_endpoint.rstrip("/")
    return f"{base}/routines/{routine_name}{suffix}?api-version={api_version}"


def build_routine_payload(
    *,
    agent_name: str,
    cron_expression: str = DEFAULT_CRON,
    time_zone: str = DEFAULT_TIME_ZONE,
    input_text: str = DEFAULT_INPUT,
    enabled: bool = True,
) -> dict[str, Any]:
    """schedule トリガー+Responses API アクションのルーチン定義。"""
    return {
        "description": (
            "Daily Hacker News AI-agent briefing (port of always_on_hn_briefing_agent; "
            "replaces Cloud Scheduler + FastAPI trigger)."
        ),
        "enabled": enabled,
        "triggers": {
            "daily-briefing": {
                "type": "schedule",
                "cron_expression": cron_expression,
                "time_zone": time_zone,
            }
        },
        "action": {
            "type": "invoke_agent_responses_api",
            "agent_name": agent_name,
            "input": input_text,
        },
    }
