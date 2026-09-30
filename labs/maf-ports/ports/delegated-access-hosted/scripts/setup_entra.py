"""Entra ID のアプリ登録・同意・ロール割り当てと Foundry 側のロール付与。**既定は dry-run**。

    # 何が行われるかを見る(通信しない・az も呼ばない)
    uv run python scripts/setup_entra.py --employee-upn alice@contoso.com --finance-upn bob@contoso.com \\
        --resource-group rg-maf-ports --base-name mafports
    # 実行(要: az login。Entra はアプリケーション管理者 / クラウドアプリケーション管理者 相当、
    #        ARM は RG の所有者 または ユーザーアクセス管理者 / RBAC 管理者 相当 — runbook §5.1)
    uv run python scripts/setup_entra.py ... --apply > .env.entra   # 最後に .env 用の行を stdout へ出す

手順(冪等。詳細は src/delegated_access_maf/provisioning/entra.py):

1. 既存の 2 利用者を UPN で解決(一般社員 / 経理担当)
2. ``<prefix>-tools-api``: 委任スコープ Tools.Access、アプリロール Suppliers.Write / Docs.Finance、v2 トークン
3. ``<prefix>-backend-api``: 委任スコープ access_as_user、公開クライアント(CLI のデバイスコード)、
   必要な権限(Tools.Access / access_as_user / openid profile offline_access)
4. OBO 用のクライアントシークレット(同名があれば作らない。``--rotate-secret`` で追加)
5. 管理者同意(oauth2PermissionGrants, AllPrincipals)
6. 経理担当に Suppliers.Write + Docs.Finance を割り当て(一般社員はロールなし)
7. バックエンドの SP に Foundry Agent Consumer と UserIdentityImpersonation のカスタムロール
   (infra/roles/foundry-user-identity-impersonation.json)をプロジェクト(既定)スコープで付与

トークンは Azure CLI から取る(``az account get-access-token``)。ログにはトークンもシークレットも
出さない。シークレットは最後の .env 用の行(stdout)にだけ出るので、ファイルへリダイレクトする。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PORT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT_ROOT / "src"))

from delegated_access_maf.provisioning.entra import (
    ApiError,
    DryRunApi,
    LiveApi,
    SetupConfig,
    env_lines,
    run_setup,
)


def _az(*args: str) -> str:
    completed = subprocess.run(["az", *args, "-o", "tsv"], check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def _token_for(resource: str) -> str:
    return _az("account", "get-access-token", "--resource", resource, "--query", "accessToken")


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Port 15 の Entra / Foundry 権限セットアップ")
    parser.add_argument("--employee-upn", default="employee@contoso.example",
                        help="一般社員役の既存ユーザー(ツール API のロールなし)")
    parser.add_argument("--finance-upn", default="finance@contoso.example",
                        help="経理担当役の既存ユーザー(Suppliers.Write + Docs.Finance)")
    parser.add_argument("--prefix", default="dah", help="アプリ登録名の接頭辞(<prefix>-tools-api 等)")
    parser.add_argument("--subscription-id", default=None, help="既定は az account show")
    parser.add_argument("--resource-group", default=None, help="共有基盤の RG(Foundry のロール用)")
    parser.add_argument("--base-name", default=None, help="共有基盤の baseName(アカウント名 aif-<baseName>)")
    parser.add_argument("--foundry-account", default=None, help="Foundry アカウント名(--base-name より優先)")
    parser.add_argument("--project", default="maf-ports", help="Foundry プロジェクト名")
    parser.add_argument("--role-scope", choices=["project", "account"], default="project",
                        help="Foundry Agent Consumer / カスタムロールの割り当てスコープ")
    parser.add_argument("--secret-days", type=int, default=30, help="クライアントシークレットの有効日数")
    parser.add_argument("--rotate-secret", action="store_true", help="既存があってもシークレットを追加発行")
    parser.add_argument("--skip-foundry-roles", action="store_true", help="手順 7(ARM)を行わない")
    parser.add_argument("--apply", action="store_true", help="実際に変更する(既定は dry-run)")
    args = parser.parse_args()

    foundry_account = args.foundry_account or (f"aif-{args.base_name}" if args.base_name else None)
    if args.apply:
        tenant_id = _az("account", "show", "--query", "tenantId")
        subscription_id = args.subscription_id or _az("account", "show", "--query", "id")
        api = LiveApi(_token_for, emit=_log)
    else:
        tenant_id = "<tenant-id>"
        subscription_id = args.subscription_id or "<subscription-id>"
        api = DryRunApi(emit=_log)

    cfg = SetupConfig(
        employee_upn=args.employee_upn,
        finance_upn=args.finance_upn,
        prefix=args.prefix,
        tenant_id=tenant_id,
        subscription_id=subscription_id,
        resource_group=args.resource_group or ("<resource-group>" if not args.apply else None),
        foundry_account=foundry_account or ("<foundry-account>" if not args.apply else None),
        project=args.project,
        role_scope=args.role_scope,
        secret_days=args.secret_days,
        rotate_secret=args.rotate_secret,
        skip_foundry_roles=args.skip_foundry_roles,
    )
    try:
        result = run_setup(api, cfg, emit=_log)
    except (ApiError, ValueError) as exc:
        _log(f"error: {exc}")
        sys.exit(1)
    if not args.apply:
        _log(f"[dry-run] {len(api.calls)} 件の呼び出しを表示した(送信していない)。--apply で実行する")
    print("\n".join(env_lines(result)))


if __name__ == "__main__":
    main()
