"""Routines(プレビュー)の作成・操作(REST・ライブ専用)。

    uv sync --extra dev --extra hosting
    az login
    uv run python scripts/setup_routine.py create                 # 平日 9:00 JST の日次ルーチン
    uv run python scripts/setup_routine.py create --cron "0 7 * * *" --time-zone UTC
    uv run python scripts/setup_routine.py dispatch               # 手動テスト実行(:dispatch_async)
    uv run python scripts/setup_routine.py runs                   # 実行履歴
    uv run python scripts/setup_routine.py show | disable | enable | delete
    uv run python scripts/setup_routine.py create --dry-run       # ペイロード確認のみ

契約(実装前調査 how-to/use-routines、2026-07): PUT
``{project_endpoint}/routines/{name}``、全リクエストに
``Foundry-Features: Routines=V1Preview`` ヘッダー、トークンのリソースは
``https://ai.azure.com``。ペイロード組み立ては routine_setup.py の純関数
(オフラインテストで固定)。SDK 代替は
``client.beta.routines.create_or_update``(azure-ai-projects>=2.2)だが、
プレビュー機能はフィーチャーヘッダー含め REST が一次契約なので REST で書く。

前提: hosted agent がデプロイ済み(hosting/deploy_hosted_agent.py)。
Japan East は Routines プレビュー対応リージョン(routine_setup.py 参照)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

PORT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT_ROOT / "src"))

from hn_briefing_maf.config import ConfigError, FoundrySettings
from hn_briefing_maf.routine_setup import (
    DEFAULT_CRON,
    DEFAULT_INPUT,
    DEFAULT_ROUTINE_NAME,
    DEFAULT_TIME_ZONE,
    ROUTINES_FEATURE_HEADER,
    TOKEN_SCOPE,
    build_routine_payload,
    routine_url,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="hn-briefing の日次 Routine(プレビュー)")
    parser.add_argument(
        "command",
        choices=["create", "show", "list", "enable", "disable", "dispatch", "runs", "delete"],
    )
    parser.add_argument("--name", default=DEFAULT_ROUTINE_NAME, help="ルーチン名")
    parser.add_argument("--agent-name", default=None, help="呼び出す hosted agent 名")
    parser.add_argument("--cron", default=DEFAULT_CRON, help="cron 式(最小間隔 5 分)")
    parser.add_argument("--time-zone", default=DEFAULT_TIME_ZONE, help="IANA タイムゾーン")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="エージェントへ送るプロンプト")
    parser.add_argument("--dry-run", action="store_true", help="create のペイロード表示のみ")
    args = parser.parse_args()

    try:
        settings = FoundrySettings.from_env()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    if not settings.project_endpoint:
        print(
            "error: FOUNDRY_PROJECT_ENDPOINT が未設定(Routine 操作はプロジェクト"
            "エンドポイント+Entra ID が必要。labs/maf-ports/.env を確認)",
            file=sys.stderr,
        )
        sys.exit(2)

    payload = build_routine_payload(
        agent_name=args.agent_name or settings.agent_name,
        cron_expression=args.cron,
        time_zone=args.time_zone,
        input_text=args.input,
    )
    if args.command == "create" and args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token(TOKEN_SCOPE).token
    headers = {"Authorization": f"Bearer {token}", **ROUTINES_FEATURE_HEADER}
    endpoint = settings.project_endpoint

    with httpx.Client(headers=headers, timeout=30.0) as http:
        if args.command == "create":
            response = http.put(routine_url(endpoint, args.name), json=payload)
        elif args.command == "show":
            response = http.get(routine_url(endpoint, args.name))
        elif args.command == "list":
            response = http.get(f"{endpoint.rstrip('/')}/routines?api-version=v1")
        elif args.command == "runs":
            response = http.get(routine_url(endpoint, args.name, suffix="/runs"))
        elif args.command == "delete":
            response = http.delete(routine_url(endpoint, args.name))
        else:  # enable / disable / dispatch
            suffix = {
                "enable": ":enable",
                "disable": ":disable",
                "dispatch": ":dispatch_async",
            }[args.command]
            response = http.post(routine_url(endpoint, args.name, suffix=suffix))

    print(f"HTTP {response.status_code}", file=sys.stderr)
    body = response.text.strip()
    if body:
        try:
            print(json.dumps(response.json(), ensure_ascii=False, indent=2))
        except ValueError:
            print(body)
    if response.status_code >= 400:
        sys.exit(1)


if __name__ == "__main__":
    main()
