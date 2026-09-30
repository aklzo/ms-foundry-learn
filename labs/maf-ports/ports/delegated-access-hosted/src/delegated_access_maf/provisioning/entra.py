"""Entra ID と Foundry 側の権限セットアップ(``scripts/setup_entra.py`` の本体)。

作るもの(すべて冪等。2 回目以降は差分だけ適用する):

1. アプリ登録 ``<prefix>-tools-api``(MCP サーバー群をまとめた 1 つのリソース API)
   - 委任スコープ ``Tools.Access``(type=Admin: OBO は利用者に同意画面を出せないので管理者同意前提)
   - アプリロール ``Suppliers.Write`` / ``Docs.Finance``(利用者に割り当てる → 委任トークンの ``roles``)
   - ``requestedAccessTokenVersion = 2``(``aud`` = クライアント ID、``iss`` = ``…/v2.0``)
2. アプリ登録 ``<prefix>-backend-api``(中間層バックエンド。CLI のデバイスコードログインも同じアプリ)
   - 委任スコープ ``access_as_user``(CLI が取るトークンの宛先)
   - パブリッククライアントフロー有効(``isFallbackPublicClient``。デバイスコード用)
   - クライアントシークレット(OBO 交換と Foundry 用トークンの取得に使う)
   - 必要な権限: ツール API の ``Tools.Access`` / 自分の ``access_as_user`` / Graph の OIDC 3 種
3. 管理者同意(``oauth2PermissionGrants`` を AllPrincipals で作成)
4. 既存の 2 利用者へのアプリロール割り当て(一般社員 = なし / 経理 = 2 ロール)
5. Foundry 側(ARM): バックエンドのサービスプリンシパルに
   **Foundry Agent Consumer** とカスタムロール(``UserIdentityImpersonation/action`` のみ)を
   プロジェクト(既定)またはアカウントのスコープで割り当てる

冪等性の作り方: アプリは Graph の upsert(``PATCH /applications(uniqueName=…)`` +
``Prefer: create-if-missing``)、スコープ / ロール ID は名前から決まる UUIDv5(再実行で同じ ID)、
同意・割り当ては「読んでから足りない分だけ作る」、ARM のロール割り当て名も UUIDv5。
シークレットだけは再取得できないので、同名の資格情報があれば作らない(``--rotate-secret`` で追加)。

Graph / ARM の呼び出しは ``Api`` 越しに行う。``DryRunApi`` は通信せずに呼び出しを表示し、
続く呼び出しが組み立てられるようにプレースホルダーの ID を返す(= dry-run の表示は実行時の
呼び出し列そのもの)。``LiveApi`` は Azure CLI のトークンで httpx を使う。
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx

from ..contracts import (
    BACKEND_API_SCOPE_NAME,
    ROLE_DOCS_FINANCE,
    ROLE_SUPPLIERS_WRITE,
    TOOLS_API_SCOPE_NAME,
)

PORT_ROOT = Path(__file__).resolve().parents[3]
ROLE_DEFINITION_FILE = PORT_ROOT / "infra" / "roles" / "foundry-user-identity-impersonation.json"

GRAPH = "https://graph.microsoft.com/v1.0"
ARM = "https://management.azure.com"
ARM_AUTHZ_API_VERSION = "2022-04-01"

#: Microsoft Graph の appId(OIDC スコープの同意先)
MS_GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"
#: Graph の委任権限 ID(permissions-reference で確認。MSAL は常にこの 3 つを要求する)
GRAPH_OIDC_SCOPE_IDS = {
    "openid": "37f7f235-527c-4136-accd-4a02d197296e",
    "profile": "14dad69e-099b-42c9-810b-d002981feec1",
    "offline_access": "7427e0e9-2fba-42fe-b0c0-848c9e6a8182",
}
#: Foundry Agent Consumer(エージェントのエンドポイントを呼ぶだけの最小ロール。rbac-foundry で確認)
FOUNDRY_AGENT_CONSUMER_ROLE_ID = "eed3b665-ab3a-47b6-8f48-c9382fb1dad6"
#: x-ms-user-identity を送るのに必要な data action(どの組み込みロールにも含まれない)
USER_IDENTITY_IMPERSONATION_ACTION = (
    "Microsoft.CognitiveServices/accounts/AIServices/agents/endpoints/UserIdentityImpersonation/action"
)

#: 利用者の別名 → ツール API のアプリロール(devtools/fake_entra.py の USERS と同じ割り当て)
USER_ROLES: dict[str, tuple[str, ...]] = {
    "employee": (),
    "finance": (ROLE_SUPPLIERS_WRITE, ROLE_DOCS_FINANCE),
}

# スコープ / ロール / ロール割り当ての ID を名前から決めるための名前空間(値そのものに意味はない)
_ID_NAMESPACE = uuid.UUID("5d0a3f6e-1b7c-4f25-9a51-0c2d6a1e7f15")


def stable_id(*parts: str) -> str:
    """名前から決まる UUIDv5。再実行しても同じ ID になる(Graph の PATCH / ARM の PUT が冪等になる)。"""
    return str(uuid.uuid5(_ID_NAMESPACE, "/".join(parts)))


# --- 設定 -----------------------------------------------------------------------------


@dataclass(frozen=True)
class SetupConfig:
    """setup_entra.py の引数。dry-run 用にテナント・サブスクリプションはプレースホルダーを既定にする。"""

    employee_upn: str
    finance_upn: str
    prefix: str = "dah"
    tenant_id: str = "<tenant-id>"
    subscription_id: str = "<subscription-id>"
    resource_group: str | None = None
    foundry_account: str | None = None
    project: str = "maf-ports"
    role_scope: Literal["project", "account"] = "project"
    secret_days: int = 30
    rotate_secret: bool = False
    skip_foundry_roles: bool = False

    @property
    def tools_app_name(self) -> str:
        return f"{self.prefix}-tools-api"

    @property
    def backend_app_name(self) -> str:
        return f"{self.prefix}-backend-api"

    @property
    def secret_label(self) -> str:
        return f"{self.prefix}-backend-obo"

    @property
    def resource_group_scope(self) -> str:
        return f"/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}"

    @property
    def foundry_scope(self) -> str:
        """Foundry Agent Consumer とカスタムロールの割り当てスコープ。"""
        account = (
            f"{self.resource_group_scope}/providers/Microsoft.CognitiveServices/accounts/"
            f"{self.foundry_account}"
        )
        return account if self.role_scope == "account" else f"{account}/projects/{self.project}"


# --- アプリ登録のマニフェスト(純関数)------------------------------------------------------


def _scope(app: str, value: str, *, admin_only: bool, title: str, description: str) -> dict:
    return {
        "id": stable_id(app, "scope", value),
        "value": value,
        "type": "Admin" if admin_only else "User",
        "isEnabled": True,
        "adminConsentDisplayName": title,
        "adminConsentDescription": description,
        "userConsentDisplayName": title,
        "userConsentDescription": description,
    }


def _app_role(app: str, value: str, *, title: str, description: str) -> dict:
    return {
        "id": stable_id(app, "appRole", value),
        "value": value,
        "displayName": title,
        "description": description,
        "allowedMemberTypes": ["User"],  # 利用者に割り当てる(アプリ権限にはしない)
        "isEnabled": True,
    }


def tools_scope_id(cfg: SetupConfig) -> str:
    return stable_id(cfg.tools_app_name, "scope", TOOLS_API_SCOPE_NAME)


def backend_scope_id(cfg: SetupConfig) -> str:
    return stable_id(cfg.backend_app_name, "scope", BACKEND_API_SCOPE_NAME)


def app_role_id(cfg: SetupConfig, role: str) -> str:
    return stable_id(cfg.tools_app_name, "appRole", role)


def tools_app_manifest(cfg: SetupConfig) -> dict:
    """ツール API のアプリ登録(upsert の本文)。identifierUris は appId が決まってから別 PATCH。"""
    name = cfg.tools_app_name
    return {
        "displayName": name,
        "signInAudience": "AzureADMyOrg",
        "api": {
            "requestedAccessTokenVersion": 2,
            "oauth2PermissionScopes": [
                _scope(
                    name,
                    TOOLS_API_SCOPE_NAME,
                    admin_only=True,
                    title="社内ツール(MCP)へのアクセス",
                    description="サインインした利用者の権限で社内文書検索と取引先マスタの MCP ツールを呼ぶ",
                )
            ],
        },
        "appRoles": [
            _app_role(
                name,
                ROLE_SUPPLIERS_WRITE,
                title="取引先マスタの更新",
                description="取引先の支払条件を更新できる(supplier-admin の MCP サーバー)",
            ),
            _app_role(
                name,
                ROLE_DOCS_FINANCE,
                title="経理向け社内文書の閲覧",
                description="Docs.Finance ラベルの社内文書を検索結果に含める",
            ),
        ],
    }


def backend_app_manifest(cfg: SetupConfig) -> dict:
    """中間層バックエンドのアプリ登録(upsert の本文)。自分自身への権限は appId 確定後に PATCH。"""
    name = cfg.backend_app_name
    return {
        "displayName": name,
        "signInAudience": "AzureADMyOrg",
        # CLI のデバイスコードログインを同じアプリで受ける(ラボの簡略化。本番はクライアントを分ける)
        "isFallbackPublicClient": True,
        "api": {
            "requestedAccessTokenVersion": 2,
            "oauth2PermissionScopes": [
                _scope(
                    name,
                    BACKEND_API_SCOPE_NAME,
                    admin_only=False,
                    title="社内アシスタントの利用",
                    description="サインインした利用者として社内アシスタント(中間層 API)を呼ぶ",
                )
            ],
        },
    }


def backend_app_patch(cfg: SetupConfig, *, backend_app_id: str, tools_app_id: str) -> dict:
    """appId 確定後の PATCH: App ID URI と必要な権限(ツール API・自分自身・Graph の OIDC)。"""
    return {
        "identifierUris": [f"api://{backend_app_id}"],
        "requiredResourceAccess": [
            {
                "resourceAppId": tools_app_id,
                "resourceAccess": [{"id": tools_scope_id(cfg), "type": "Scope"}],
            },
            {
                "resourceAppId": backend_app_id,
                "resourceAccess": [{"id": backend_scope_id(cfg), "type": "Scope"}],
            },
            {
                "resourceAppId": MS_GRAPH_APP_ID,
                "resourceAccess": [
                    {"id": scope_id, "type": "Scope"} for scope_id in GRAPH_OIDC_SCOPE_IDS.values()
                ],
            },
        ],
    }


def load_role_template(path: Path = ROLE_DEFINITION_FILE) -> dict:
    """infra/roles/ のカスタムロール定義(``az role definition create`` 形式)を読む。"""
    return json.loads(path.read_text(encoding="utf-8"))


def custom_role_name(cfg: SetupConfig, template: Mapping[str, Any]) -> str:
    # カスタムロール名はテナント内で一意。RG 名を足して他の検証環境と衝突させない
    return f"{template['Name']} ({cfg.resource_group})"


def role_definition_body(cfg: SetupConfig, template: Mapping[str, Any]) -> dict:
    """ARM の roleDefinitions PUT 本文。割り当て可能スコープは RG(RBAC の一般規則: MG / サブスク / RG)。"""
    return {
        "properties": {
            "roleName": custom_role_name(cfg, template),
            "description": template["Description"],
            "type": "CustomRole",
            "permissions": [
                {
                    "actions": list(template.get("Actions", [])),
                    "notActions": list(template.get("NotActions", [])),
                    "dataActions": list(template["DataActions"]),
                    "notDataActions": list(template.get("NotDataActions", [])),
                }
            ],
            "assignableScopes": [cfg.resource_group_scope],
        }
    }


def env_lines(result: SetupResult) -> list[str]:
    """ポートの .env に転記する行(スクリプトが最後に stdout へ出す)。"""
    secret = result.backend_client_secret or (
        "<既存のシークレットを使う。紛失したら --rotate-secret で追加発行>"
    )
    return [
        "# --- scripts/setup_entra.py の出力(ポートの .env に転記)---",
        f"ENTRA_TENANT_ID={result.tenant_id}",
        f"TOOLS_API_CLIENT_ID={result.tools_app_id}",
        f"TOOLS_API_SCOPE=api://{result.tools_app_id}/{TOOLS_API_SCOPE_NAME}",
        f"BACKEND_API_CLIENT_ID={result.backend_app_id}",
        f"BACKEND_CLIENT_SECRET={secret}",
        f"# CLI が要求するスコープ: api://{result.backend_app_id}/{BACKEND_API_SCOPE_NAME}",
        "# infra/main.bicep の toolsApiClientId にも TOOLS_API_CLIENT_ID を渡す",
    ]


# --- HTTP 抽象 --------------------------------------------------------------------------


class ApiError(RuntimeError):
    def __init__(self, method: str, url: str, status: int, body: Any) -> None:
        super().__init__(f"{method} {url} -> HTTP {status}: {body}")
        self.status = status
        self.body = body


@dataclass(frozen=True)
class ApiResponse:
    status: int
    body: dict[str, Any]


class Api(Protocol):
    def call(
        self,
        method: str,
        url: str,
        *,
        json_body: dict | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        ok_statuses: tuple[int, ...] = (),
        retry_statuses: tuple[int, ...] = (),
    ) -> ApiResponse: ...


def _describe(method: str, url: str, params: dict[str, str] | None) -> str:
    query = "&".join(f"{k}={v}" for k, v in (params or {}).items())
    return f"{method} {url}{'?' + query if query else ''}"


@dataclass
class DryRunApi:
    """通信しない。呼び出しを ``emit`` へ表示し、後続の呼び出しを組み立てられる値を返す。

    ID はプレースホルダー(例 ``<dah-tools-api:appId>``)。存在確認の一覧は常に空を返すので、
    「初回実行で作られるもの」がすべて表示される。
    """

    emit: Callable[[str], None] = print
    calls: list[tuple[str, str]] = field(default_factory=list)

    def call(self, method, url, *, json_body=None, params=None, headers=None, ok_statuses=(),
             retry_statuses=()) -> ApiResponse:
        line = _describe(method, url, params)
        self.calls.append((method, line))
        extra = f"  [{', '.join(f'{k}: {v}' for k, v in headers.items())}]" if headers else ""
        self.emit(f"[dry-run] {line}{extra}")
        if json_body is not None:
            for body_line in json.dumps(json_body, ensure_ascii=False, indent=2).splitlines():
                self.emit(f"          {body_line}")
        return ApiResponse(200, self._placeholder(method, url, params or {}))

    @staticmethod
    def _placeholder(method: str, url: str, params: Mapping[str, str]) -> dict[str, Any]:
        if method != "GET" and not url.endswith("/addPassword"):
            return {}
        if url.endswith("/addPassword"):
            return {"secretText": "<apply 時に発行される値>"}
        if "$filter" in params or url.endswith("/appRoleAssignments"):
            return {"value": []}
        if m := re.search(r"/users/([^/?]+)$", url):
            return {"id": f"<{m.group(1)}:oid>"}
        if m := re.search(r"/applications\(uniqueName='([^']+)'\)$", url):
            name = m.group(1)
            return {
                "id": f"<{name}:objectId>",
                "appId": f"<{name}:appId>",
                "identifierUris": [],
                "passwordCredentials": [],
            }
        if m := re.search(r"/servicePrincipals\(appId='([^']+)'\)$", url):
            app_id = m.group(1)
            if app_id == MS_GRAPH_APP_ID:
                return {"id": "<MicrosoftGraph:spId>"}
            if pm := re.fullmatch(r"<(.+):appId>", app_id):
                return {"id": f"<{pm.group(1)}:spId>"}
            return {"id": f"<sp:{app_id}>"}
        return {}


TokenProvider = Callable[[str], str]


class LiveApi:
    """Azure CLI のトークン(``token_for(resource)``)で Graph / ARM を呼ぶ。

    新規作成直後のアプリ・サービスプリンシパル・カスタムロールはレプリケーション遅延で
    一時的に 400 / 404 になるため、``retry_statuses`` を指定した呼び出しは再試行する。
    """

    def __init__(
        self,
        token_for: TokenProvider,
        *,
        client: httpx.Client | None = None,
        emit: Callable[[str], None] = print,
        attempts: int = 8,
        delay: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._token_for = token_for
        self._client = client or httpx.Client(timeout=60.0)
        self._emit = emit
        self._attempts = attempts
        self._delay = delay
        self._sleep = sleep
        self._tokens: dict[str, str] = {}

    def _token(self, url: str) -> str:
        resource = GRAPH.rsplit("/", 1)[0] if url.startswith(GRAPH) else ARM
        if resource not in self._tokens:
            self._tokens[resource] = self._token_for(resource)
        return self._tokens[resource]

    def call(self, method, url, *, json_body=None, params=None, headers=None, ok_statuses=(),
             retry_statuses=()) -> ApiResponse:
        self._emit(f"[apply] {_describe(method, url, params)}")
        all_headers = {"Authorization": f"Bearer {self._token(url)}", **(headers or {})}
        for attempt in range(1, self._attempts + 1):
            response = self._client.request(
                method, url, json=json_body, params=params, headers=all_headers
            )
            status = response.status_code
            body: dict[str, Any] = {}
            if response.content:
                try:
                    body = response.json()
                except ValueError:
                    body = {"raw": response.text[:500]}
            if status < 400 or status in ok_statuses:
                return ApiResponse(status, body)
            if status in retry_statuses and attempt < self._attempts:
                self._emit(f"  HTTP {status}(レプリケーション待ち)— {self._delay:.0f} 秒後に再試行")
                self._sleep(self._delay)
                continue
            raise ApiError(method, url, status, body)
        raise AssertionError("unreachable")  # pragma: no cover


# --- 手順本体 -----------------------------------------------------------------------------


@dataclass
class SetupResult:
    tenant_id: str
    tools_app_id: str = ""
    tools_sp_id: str = ""
    backend_app_id: str = ""
    backend_sp_id: str = ""
    backend_client_secret: str | None = None
    user_ids: dict[str, str] = field(default_factory=dict)
    custom_role_id: str | None = None


UPSERT = {"Prefer": "create-if-missing"}


def _upsert_app(api: Api, name: str, manifest: dict) -> dict:
    url = f"{GRAPH}/applications(uniqueName='{name}')"
    api.call("PATCH", url, json_body=manifest, headers=UPSERT)
    return api.call("GET", url, retry_statuses=(404,)).body


def _upsert_sp(api: Api, app_id: str) -> str:
    url = f"{GRAPH}/servicePrincipals(appId='{app_id}')"
    # 作成直後のアプリは SP 作成で一時的に 400/404 になりうる
    api.call(
        "PATCH",
        url,
        json_body={"appRoleAssignmentRequired": False},
        headers=UPSERT,
        retry_statuses=(400, 404),
    )
    return api.call("GET", url, retry_statuses=(404,)).body["id"]


def _ensure_identifier_uri(api: Api, app: Mapping[str, Any]) -> None:
    uri = f"api://{app['appId']}"
    if uri not in (app.get("identifierUris") or []):
        api.call("PATCH", f"{GRAPH}/applications/{app['id']}", json_body={"identifierUris": [uri]})


def ensure_grant(api: Api, *, client_sp: str, resource_sp: str, scopes: list[str]) -> None:
    """管理者同意(AllPrincipals)。既存の許可に足りないスコープだけ足す。"""
    existing = api.call(
        "GET",
        f"{GRAPH}/oauth2PermissionGrants",
        params={"$filter": f"clientId eq '{client_sp}'"},
    ).body.get("value", [])
    for grant in existing:
        if grant.get("resourceId") == resource_sp and grant.get("consentType") == "AllPrincipals":
            have = set((grant.get("scope") or "").split())
            if set(scopes) <= have:
                return
            api.call(
                "PATCH",
                f"{GRAPH}/oauth2PermissionGrants/{grant['id']}",
                json_body={"scope": " ".join(sorted(have | set(scopes)))},
            )
            return
    api.call(
        "POST",
        f"{GRAPH}/oauth2PermissionGrants",
        json_body={
            "clientId": client_sp,
            "consentType": "AllPrincipals",
            "resourceId": resource_sp,
            "scope": " ".join(scopes),
        },
        retry_statuses=(400, 404),
    )


def ensure_app_roles(api: Api, *, user_id: str, tools_sp: str, role_ids: list[str]) -> None:
    """利用者へのアプリロール割り当て。既にあるものは作らない。"""
    if not role_ids:
        return
    assigned = api.call(
        "GET",
        f"{GRAPH}/users/{user_id}/appRoleAssignments",
        params={"$filter": f"resourceId eq {tools_sp}"},
    ).body.get("value", [])
    have = {a.get("appRoleId") for a in assigned}
    for role_id in role_ids:
        if role_id in have:
            continue
        api.call(
            "POST",
            f"{GRAPH}/servicePrincipals/{tools_sp}/appRoleAssignedTo",
            json_body={"principalId": user_id, "resourceId": tools_sp, "appRoleId": role_id},
            retry_statuses=(400, 404),
        )


def ensure_custom_role(api: Api, cfg: SetupConfig, template: Mapping[str, Any]) -> str:
    """UserIdentityImpersonation だけを持つカスタムロール。既存(同名)なら再利用する。"""
    base = f"{ARM}{cfg.resource_group_scope}/providers/Microsoft.Authorization/roleDefinitions"
    name = custom_role_name(cfg, template)
    found = api.call(
        "GET",
        base,
        params={"$filter": f"roleName eq '{name}'", "api-version": ARM_AUTHZ_API_VERSION},
    ).body.get("value", [])
    if found:
        return found[0]["name"]
    role_id = stable_id("roleDefinition", cfg.subscription_id, str(cfg.resource_group), name)
    api.call(
        "PUT",
        f"{base}/{role_id}",
        params={"api-version": ARM_AUTHZ_API_VERSION},
        json_body=role_definition_body(cfg, template),
    )
    return role_id


def ensure_role_assignment(api: Api, *, scope: str, principal_id: str, role_definition_id: str,
                           subscription_id: str) -> None:
    """ARM のロール割り当て(名前は UUIDv5 で固定 → 再実行は同じ割り当てへの PUT)。"""
    full_role = (
        f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleDefinitions/"
        f"{role_definition_id}"
    )
    name = stable_id("roleAssignment", scope, principal_id, role_definition_id)
    api.call(
        "PUT",
        f"{ARM}{scope}/providers/Microsoft.Authorization/roleAssignments/{name}",
        params={"api-version": ARM_AUTHZ_API_VERSION},
        json_body={
            "properties": {
                "roleDefinitionId": full_role,
                "principalId": principal_id,
                "principalType": "ServicePrincipal",
            }
        },
        # 409 = 同じ(プリンシパル・ロール・スコープ)の割り当てが別名で既にある → 目的は達成済み
        ok_statuses=(409,),
        # 400 = 作成直後の SP / カスタムロールがまだ見えない(PrincipalNotFound 等)
        retry_statuses=(400,),
    )


def run_setup(
    api: Api,
    cfg: SetupConfig,
    *,
    emit: Callable[[str], None] = print,
    now: Callable[[], float] = time.time,
    role_template: Mapping[str, Any] | None = None,
) -> SetupResult:
    """セットアップ手順(dry-run と apply で同じコードを通る)。"""
    result = SetupResult(tenant_id=cfg.tenant_id)

    emit("# 1. 利用者(既存)の解決")
    for alias, upn in (("employee", cfg.employee_upn), ("finance", cfg.finance_upn)):
        result.user_ids[alias] = api.call("GET", f"{GRAPH}/users/{upn}").body["id"]

    emit(f"# 2. ツール API のアプリ登録 {cfg.tools_app_name}(Tools.Access + アプリロール 2 つ)")
    tools_app = _upsert_app(api, cfg.tools_app_name, tools_app_manifest(cfg))
    result.tools_app_id = tools_app["appId"]
    _ensure_identifier_uri(api, tools_app)
    result.tools_sp_id = _upsert_sp(api, result.tools_app_id)

    emit(f"# 3. 中間層バックエンドのアプリ登録 {cfg.backend_app_name}(access_as_user + 公開クライアント)")
    backend_app = _upsert_app(api, cfg.backend_app_name, backend_app_manifest(cfg))
    result.backend_app_id = backend_app["appId"]
    api.call(
        "PATCH",
        f"{GRAPH}/applications/{backend_app['id']}",
        json_body=backend_app_patch(
            cfg, backend_app_id=result.backend_app_id, tools_app_id=result.tools_app_id
        ),
    )
    result.backend_sp_id = _upsert_sp(api, result.backend_app_id)

    emit("# 4. OBO 用のクライアントシークレット(同名があれば作らない)")
    has_secret = any(
        c.get("displayName") == cfg.secret_label for c in backend_app.get("passwordCredentials") or []
    )
    if has_secret and not cfg.rotate_secret:
        emit(f"  既存のシークレット {cfg.secret_label} を使う(値は再取得できない)")
    else:
        end = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now() + cfg.secret_days * 86400))
        result.backend_client_secret = api.call(
            "POST",
            f"{GRAPH}/applications/{backend_app['id']}/addPassword",
            json_body={"passwordCredential": {"displayName": cfg.secret_label, "endDateTime": end}},
        ).body.get("secretText")

    emit("# 5. 管理者同意(OBO は同意画面を出せないので事前に付与する)")
    graph_sp = api.call("GET", f"{GRAPH}/servicePrincipals(appId='{MS_GRAPH_APP_ID}')").body["id"]
    ensure_grant(
        api, client_sp=result.backend_sp_id, resource_sp=result.tools_sp_id,
        scopes=[TOOLS_API_SCOPE_NAME],
    )
    ensure_grant(
        api, client_sp=result.backend_sp_id, resource_sp=result.backend_sp_id,
        scopes=[BACKEND_API_SCOPE_NAME],
    )
    ensure_grant(
        api, client_sp=result.backend_sp_id, resource_sp=graph_sp,
        scopes=list(GRAPH_OIDC_SCOPE_IDS),
    )

    emit("# 6. アプリロールの割り当て(一般社員 = なし / 経理 = Suppliers.Write + Docs.Finance)")
    for alias, roles in USER_ROLES.items():
        ensure_app_roles(
            api,
            user_id=result.user_ids[alias],
            tools_sp=result.tools_sp_id,
            role_ids=[app_role_id(cfg, role) for role in roles],
        )

    if cfg.skip_foundry_roles:
        emit("# 7. Foundry 側のロールはスキップ(--skip-foundry-roles)")
        return result
    if not (cfg.resource_group and cfg.foundry_account):
        raise ValueError("Foundry 側のロールには --resource-group と --foundry-account(または --base-name)が必要")

    emit(f"# 7. Foundry 側: バックエンドの SP に 2 ロール(スコープ: {cfg.role_scope})")
    template = role_template if role_template is not None else load_role_template()
    result.custom_role_id = ensure_custom_role(api, cfg, template)
    for role_id in (FOUNDRY_AGENT_CONSUMER_ROLE_ID, result.custom_role_id):
        ensure_role_assignment(
            api,
            scope=cfg.foundry_scope,
            principal_id=result.backend_sp_id,
            role_definition_id=role_id,
            subscription_id=cfg.subscription_id,
        )
    return result
