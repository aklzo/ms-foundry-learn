"""Routines(2026-09 GA)のペイロード・URL・ヘッダー組み立て(純関数)。

REST を貼るのは scripts/setup_routine.py のみ。契約は Learn の
how-to/use-routines(2026-08-27 版)から:

- ``PUT {project_endpoint}/routines/{name}?api-version=v1``(**api-version=v1 必須**
  — 2026-07 のライブ実測で判明し、現行 Learn の REST 例にも明記された)
- Bearer トークンのリソースは ``https://ai.azure.com``
- trigger: ``{"type": "schedule", "cron_expression": ..., "time_zone": ...}``
  (cron_expression / time_zone は必須。**最小間隔 5 分**)
- action: ``{"type": "invoke_agent_responses_api", "agent_name": ..., "input": ...}``
- 操作系: POST ``:enable`` / ``:disable`` / ``:dispatch_async``、GET ``/runs``(実行履歴)

**フィーチャーヘッダーは送らない(2026-09-29 変更)**: プレビュー期(2026-07)は
``Foundry-Features: Routines=V1Preview`` を全リクエストに付けていたが、GA 後の
Learn の REST 例からヘッダーは消えている。REST 仕様(azure-rest-api-specs の
routines/routes.tsp)でも ``Routines=V1Preview`` キーは 2026-08 に削除され、
後継の ``Routines=V2Preview`` は**任意(conditional)ヘッダー**扱い
(azure-ai-projects の ``client.beta.routines`` は自動付与する)。本ポートは
GA 範囲の要素(schedule トリガー+Responses API アクション)しか使わないので
ヘッダーなしが正。存在しないキー ``V1Preview`` を送り続けると拒否される恐れが
あるため削除した(ライブ未検証)。

リージョン: GA 時点で「UK West / Switzerland West / Japan West / UAE North /
Norway East **以外の全 Foundry リージョン**」(プレビュー期は Japan East を含む
8 リージョン)。共有基盤の Japan East はそのまま使える。
"""

from __future__ import annotations

from typing import Any

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


#: Routines の data-plane api-version(GA 後も ``v1``。SDK の既定値と同じ)
ROUTINES_API_VERSION = "v1"


def routine_request_headers(token: str) -> dict[str, str]:
    """Routines REST 呼び出しのヘッダー(Bearer のみ。フィーチャーヘッダーなし — 冒頭 docstring)。"""
    return {"Authorization": f"Bearer {token}"}


def routines_collection_url(project_endpoint: str, *, api_version: str = ROUTINES_API_VERSION) -> str:
    """ルーチン一覧(GET)の URL。"""
    return f"{project_endpoint.rstrip('/')}/routines?api-version={api_version}"


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
