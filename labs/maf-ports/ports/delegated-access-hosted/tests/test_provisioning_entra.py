"""scripts/setup_entra.py の本体(provisioning/entra.py)のオフラインテスト。

Graph / ARM は httpx の MockTransport で動く疑似ディレクトリ(``FakeCloud``)に置き換え、
「初回で全部作る」「2 回目は何も増やさない(冪等)」「dry-run は通信しない」を固定する。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

from delegated_access_maf.contracts import (
    BACKEND_API_SCOPE_NAME,
    ROLE_DOCS_FINANCE,
    ROLE_SUPPLIERS_WRITE,
    TOOLS_API_SCOPE_NAME,
)
from delegated_access_maf.provisioning import entra
from delegated_access_maf.provisioning.entra import (
    FOUNDRY_AGENT_CONSUMER_ROLE_ID,
    GRAPH_OIDC_SCOPE_IDS,
    MS_GRAPH_APP_ID,
    USER_IDENTITY_IMPERSONATION_ACTION,
    DryRunApi,
    LiveApi,
    SetupConfig,
    env_lines,
    run_setup,
)

PORT_ROOT = Path(__file__).resolve().parents[1]
EMPLOYEE_UPN = "alice@contoso.example"
FINANCE_UPN = "bob@contoso.example"
SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"


def _cfg(**overrides: Any) -> SetupConfig:
    values: dict[str, Any] = {
        "employee_upn": EMPLOYEE_UPN,
        "finance_upn": FINANCE_UPN,
        "tenant_id": "tenant-0001",
        "subscription_id": SUBSCRIPTION,
        "resource_group": "rg-maf-ports",
        "foundry_account": "aif-mafports",
    }
    values.update(overrides)
    return SetupConfig(**values)


# --- 疑似 Graph / ARM --------------------------------------------------------------------


class FakeCloud:
    """Graph v1.0 と ARM の、セットアップが使う操作だけを実装した疑似クラウド。"""

    def __init__(self, *, sp_not_ready: int = 0) -> None:
        self.users = {EMPLOYEE_UPN: str(uuid.uuid4()), FINANCE_UPN: str(uuid.uuid4())}
        self.apps: dict[str, dict[str, Any]] = {}  # uniqueName -> app
        self.sps: dict[str, dict[str, Any]] = {  # appId -> sp
            MS_GRAPH_APP_ID: {"id": "graph-sp", "appId": MS_GRAPH_APP_ID},
        }
        self.grants: list[dict[str, Any]] = []
        self.assignments: list[dict[str, Any]] = []
        self.role_definitions: dict[str, dict[str, Any]] = {}
        self.role_assignments: dict[str, dict[str, Any]] = {}  # full path -> body
        self.requests: list[tuple[str, str]] = []
        self.auth_headers: set[str] = set()
        self._sp_not_ready = sp_not_ready  # 作成直後の SP upsert を何回 404 にするか

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    @staticmethod
    def _json(status: int, body: Any = None) -> httpx.Response:
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status)

    def _app_by_object_id(self, object_id: str) -> dict[str, Any]:
        return next(a for a in self.apps.values() if a["id"] == object_id)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        params = dict(request.url.params)
        self.requests.append((method, path))
        self.auth_headers.add(request.headers.get("authorization", ""))
        body = json.loads(request.content) if request.content else None
        if request.url.host == "graph.microsoft.com":
            return self._graph(method, path.removeprefix("/v1.0"), params, body, request)
        return self._arm(method, path, params, body)

    def _graph(self, method, path, params, body, request) -> httpx.Response:
        upsert = request.headers.get("prefer") == "create-if-missing"
        if m := re.fullmatch(r"/users/([^/]+)", path):
            uid = self.users.get(m.group(1))
            return self._json(200, {"id": uid}) if uid else self._json(404, {"error": "nf"})
        if m := re.fullmatch(r"/applications\(uniqueName='([^']+)'\)", path):
            name = m.group(1)
            if method == "GET":
                app = self.apps.get(name)
                return self._json(200, app) if app else self._json(404, {"error": "nf"})
            assert method == "PATCH" and upsert
            if name in self.apps:
                self.apps[name].update(body)
                return self._json(204)
            self.apps[name] = {
                "id": str(uuid.uuid4()),
                "appId": str(uuid.uuid4()),
                "uniqueName": name,
                "identifierUris": [],
                "passwordCredentials": [],
                **body,
            }
            return self._json(201, self.apps[name])
        if m := re.fullmatch(r"/applications/([^/]+)/addPassword", path):
            app = self._app_by_object_id(m.group(1))
            app["passwordCredentials"].append(
                {"displayName": body["passwordCredential"]["displayName"], "keyId": "k"}
            )
            return self._json(200, {"secretText": f"secret-{len(app['passwordCredentials'])}"})
        if m := re.fullmatch(r"/applications/([^/]+)", path):
            self._app_by_object_id(m.group(1)).update(body)
            return self._json(204)
        if m := re.fullmatch(r"/servicePrincipals\(appId='([^']+)'\)", path):
            app_id = m.group(1)
            if method == "GET":
                sp = self.sps.get(app_id)
                return self._json(200, sp) if sp else self._json(404, {"error": "nf"})
            assert method == "PATCH" and upsert
            if app_id not in self.sps and self._sp_not_ready > 0:
                self._sp_not_ready -= 1
                return self._json(404, {"error": "app not replicated yet"})
            if app_id in self.sps:
                self.sps[app_id].update(body)
                return self._json(204)
            self.sps[app_id] = {"id": str(uuid.uuid4()), "appId": app_id, **body}
            return self._json(201, self.sps[app_id])
        if path == "/oauth2PermissionGrants":
            if method == "GET":
                client = re.fullmatch(r"clientId eq '([^']+)'", params["$filter"]).group(1)
                return self._json(200, {"value": [g for g in self.grants if g["clientId"] == client]})
            grant = {"id": str(uuid.uuid4()), **body}
            self.grants.append(grant)
            return self._json(201, grant)
        if m := re.fullmatch(r"/oauth2PermissionGrants/([^/]+)", path):
            next(g for g in self.grants if g["id"] == m.group(1)).update(body)
            return self._json(204)
        if m := re.fullmatch(r"/users/([^/]+)/appRoleAssignments", path):
            resource = re.fullmatch(r"resourceId eq (\S+)", params["$filter"]).group(1)
            value = [
                a
                for a in self.assignments
                if a["principalId"] == m.group(1) and a["resourceId"] == resource
            ]
            return self._json(200, {"value": value})
        if m := re.fullmatch(r"/servicePrincipals/([^/]+)/appRoleAssignedTo", path):
            assert body["resourceId"] == m.group(1)
            self.assignments.append({"id": str(uuid.uuid4()), **body})
            return self._json(201, self.assignments[-1])
        raise AssertionError(f"unexpected Graph call {method} {path}")

    def _arm(self, method, path, params, body) -> httpx.Response:
        assert params.get("api-version") == entra.ARM_AUTHZ_API_VERSION
        if path.endswith("/providers/Microsoft.Authorization/roleDefinitions"):
            name = re.fullmatch(r"roleName eq '(.+)'", params["$filter"]).group(1)
            value = [
                {"name": rid, **d}
                for rid, d in self.role_definitions.items()
                if d["properties"]["roleName"] == name
            ]
            return self._json(200, {"value": value})
        if m := re.search(r"/providers/Microsoft\.Authorization/roleDefinitions/([^/]+)$", path):
            self.role_definitions[m.group(1)] = body
            return self._json(201, body)
        if "/providers/Microsoft.Authorization/roleAssignments/" in path:
            scope = path.split("/providers/Microsoft.Authorization/roleAssignments/")[0]
            props = body["properties"]
            for other_path, other in self.role_assignments.items():
                same = (
                    other_path.startswith(scope + "/")
                    and other["properties"]["principalId"] == props["principalId"]
                    and other["properties"]["roleDefinitionId"] == props["roleDefinitionId"]
                )
                if same and other_path != path:
                    return self._json(409, {"error": {"code": "RoleAssignmentExists"}})
            created = path not in self.role_assignments
            self.role_assignments[path] = body
            return self._json(201 if created else 200, body)
        raise AssertionError(f"unexpected ARM call {method} {path}")


def _live(cloud: FakeCloud, lines: list[str] | None = None) -> LiveApi:
    return LiveApi(
        lambda resource: f"token-for-{resource}",
        client=httpx.Client(transport=cloud.transport()),
        emit=(lines.append if lines is not None else lambda _m: None),
        sleep=lambda _s: None,
    )


# --- マニフェスト(純関数)------------------------------------------------------------------


def test_tools_app_exposes_scope_and_user_assignable_roles_with_v2_tokens():
    manifest = entra.tools_app_manifest(_cfg())
    assert manifest["api"]["requestedAccessTokenVersion"] == 2
    [scope] = manifest["api"]["oauth2PermissionScopes"]
    assert scope["value"] == TOOLS_API_SCOPE_NAME
    assert scope["type"] == "Admin"  # OBO は同意画面を出せない → 管理者同意前提
    roles = {r["value"]: r for r in manifest["appRoles"]}
    assert set(roles) == {ROLE_SUPPLIERS_WRITE, ROLE_DOCS_FINANCE}
    assert all(r["allowedMemberTypes"] == ["User"] for r in roles.values())


def test_backend_app_is_public_client_with_access_as_user_and_needs_tools_scope():
    cfg = _cfg()
    manifest = entra.backend_app_manifest(cfg)
    assert manifest["isFallbackPublicClient"] is True
    assert manifest["api"]["requestedAccessTokenVersion"] == 2
    assert [s["value"] for s in manifest["api"]["oauth2PermissionScopes"]] == [
        BACKEND_API_SCOPE_NAME
    ]
    patch = entra.backend_app_patch(cfg, backend_app_id="B", tools_app_id="T")
    assert patch["identifierUris"] == ["api://B"]
    rra = {r["resourceAppId"]: {a["id"] for a in r["resourceAccess"]} for r in patch[
        "requiredResourceAccess"]}
    assert rra["T"] == {entra.tools_scope_id(cfg)}
    assert rra["B"] == {entra.backend_scope_id(cfg)}
    assert rra[MS_GRAPH_APP_ID] == set(GRAPH_OIDC_SCOPE_IDS.values())


def test_ids_are_stable_across_runs_and_distinct():
    a, b = _cfg(), _cfg()
    assert entra.tools_app_manifest(a) == entra.tools_app_manifest(b)
    ids = {
        entra.tools_scope_id(a),
        entra.backend_scope_id(a),
        entra.app_role_id(a, ROLE_SUPPLIERS_WRITE),
        entra.app_role_id(a, ROLE_DOCS_FINANCE),
    }
    assert len(ids) == 4
    # 接頭辞を変えると別のアプリ = 別の ID
    assert entra.tools_scope_id(_cfg(prefix="other")) not in ids


def test_custom_role_grants_only_the_impersonation_data_action():
    template = entra.load_role_template()
    assert template["DataActions"] == [USER_IDENTITY_IMPERSONATION_ACTION]
    assert template["Actions"] == [] and template["NotDataActions"] == []
    body = entra.role_definition_body(_cfg(), template)["properties"]
    assert body["type"] == "CustomRole"
    assert body["permissions"][0]["dataActions"] == [USER_IDENTITY_IMPERSONATION_ACTION]
    assert body["assignableScopes"] == [
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-maf-ports"
    ]
    assert body["roleName"].endswith("(rg-maf-ports)")  # テナント内で一意にする


def test_foundry_scope_project_or_account():
    account = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-maf-ports/providers/"
        "Microsoft.CognitiveServices/accounts/aif-mafports"
    )
    assert _cfg().foundry_scope == f"{account}/projects/maf-ports"
    assert _cfg(role_scope="account").foundry_scope == account


# --- dry-run --------------------------------------------------------------------------------


def test_dry_run_prints_every_call_and_never_touches_the_network(monkeypatch):
    def no_network(*_a, **_k):
        raise AssertionError("dry-run must not send requests")

    monkeypatch.setattr(httpx.Client, "request", no_network)
    printed: list[str] = []
    api = DryRunApi(emit=printed.append)
    result = run_setup(api, _cfg(), emit=printed.append)

    methods = [m for m, _ in api.calls]
    assert methods.count("POST") >= 6  # シークレット 1 + 同意 3 + 経理のロール 2
    joined = "\n".join(printed)
    for fragment in (
        "applications(uniqueName='dah-tools-api')",
        "applications(uniqueName='dah-backend-api')",
        "Prefer: create-if-missing",
        "/oauth2PermissionGrants",
        "/appRoleAssignedTo",
        "roleDefinitions",
        FOUNDRY_AGENT_CONSUMER_ROLE_ID,
        USER_IDENTITY_IMPERSONATION_ACTION,
    ):
        assert fragment in joined, fragment
    # 一般社員にはロールを割り当てない(経理だけ 2 件)
    assert sum("appRoleAssignedTo" in line for _m, line in api.calls) == 2
    assert result.tools_app_id == "<dah-tools-api:appId>"


def test_dry_run_script_calls_neither_az_nor_http(monkeypatch, capsys):
    import subprocess

    def forbidden(*_a, **_k):
        raise AssertionError("dry-run must not call az / HTTP")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)
    spec = importlib.util.spec_from_file_location(
        "setup_entra_script", PORT_ROOT / "scripts" / "setup_entra.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["setup_entra.py", "--resource-group", "rg", "--base-name", "x"])
    module.main()
    out = capsys.readouterr().out
    for name in (
        "ENTRA_TENANT_ID=",
        "TOOLS_API_CLIENT_ID=",
        "TOOLS_API_SCOPE=api://",
        "BACKEND_API_CLIENT_ID=",
        "BACKEND_CLIENT_SECRET=",
    ):
        assert name in out


# --- 実行経路(疑似クラウド)----------------------------------------------------------------


def test_apply_creates_everything_and_second_run_is_a_no_op():
    cloud = FakeCloud()
    first = run_setup(_live(cloud), _cfg(), emit=lambda _m: None)

    tools = cloud.apps["dah-tools-api"]
    backend = cloud.apps["dah-backend-api"]
    assert first.tools_app_id == tools["appId"]
    assert tools["identifierUris"] == [f"api://{tools['appId']}"]
    assert backend["identifierUris"] == [f"api://{backend['appId']}"]
    assert first.backend_client_secret == "secret-1"
    tools_sp = cloud.sps[tools["appId"]]["id"]
    backend_sp = cloud.sps[backend["appId"]]["id"]
    grants = {(g["resourceId"], g["scope"]) for g in cloud.grants}
    assert grants == {
        (tools_sp, TOOLS_API_SCOPE_NAME),
        (backend_sp, BACKEND_API_SCOPE_NAME),
        ("graph-sp", "openid profile offline_access"),
    }
    assert all(g["clientId"] == backend_sp and g["consentType"] == "AllPrincipals"
               for g in cloud.grants)
    finance_roles = {a["appRoleId"] for a in cloud.assignments
                     if a["principalId"] == cloud.users[FINANCE_UPN]}
    assert finance_roles == {entra.app_role_id(_cfg(), ROLE_SUPPLIERS_WRITE),
                             entra.app_role_id(_cfg(), ROLE_DOCS_FINANCE)}
    assert not [a for a in cloud.assignments if a["principalId"] == cloud.users[EMPLOYEE_UPN]]
    assigned_roles = {b["properties"]["roleDefinitionId"].rsplit("/", 1)[1]
                      for b in cloud.role_assignments.values()}
    assert assigned_roles == {FOUNDRY_AGENT_CONSUMER_ROLE_ID, first.custom_role_id}
    assert all(p.startswith(_cfg().foundry_scope + "/") for p in cloud.role_assignments)
    assert all(b["properties"]["principalId"] == backend_sp
               for b in cloud.role_assignments.values())

    snapshot = (len(cloud.apps), len(cloud.sps), len(cloud.grants), len(cloud.assignments),
                len(cloud.role_definitions), len(cloud.role_assignments))
    cloud.requests.clear()
    second = run_setup(_live(cloud), _cfg(), emit=lambda _m: None)
    assert second.tools_app_id == first.tools_app_id
    assert second.backend_client_secret is None  # 既存のシークレットは作り直さない
    assert (len(cloud.apps), len(cloud.sps), len(cloud.grants), len(cloud.assignments),
            len(cloud.role_definitions), len(cloud.role_assignments)) == snapshot
    assert not [r for r in cloud.requests if r[0] == "POST"]
    assert second.custom_role_id == first.custom_role_id


def test_rotate_secret_adds_a_new_credential():
    cloud = FakeCloud()
    run_setup(_live(cloud), _cfg(), emit=lambda _m: None)
    rotated = run_setup(_live(cloud), _cfg(rotate_secret=True), emit=lambda _m: None)
    assert rotated.backend_client_secret == "secret-2"


def test_missing_grant_scope_is_patched_not_duplicated():
    cloud = FakeCloud()
    run_setup(_live(cloud), _cfg(), emit=lambda _m: None)
    graph_grant = next(g for g in cloud.grants if g["resourceId"] == "graph-sp")
    graph_grant["scope"] = "openid"  # 誰かが手で狭めた
    run_setup(_live(cloud), _cfg(), emit=lambda _m: None)
    assert len(cloud.grants) == 3
    assert set(graph_grant["scope"].split()) == set(GRAPH_OIDC_SCOPE_IDS)


def test_replication_delay_is_retried():
    cloud = FakeCloud(sp_not_ready=2)
    result = run_setup(_live(cloud), _cfg(), emit=lambda _m: None)
    assert result.tools_sp_id and result.backend_sp_id


def test_logs_never_contain_tokens_or_the_secret():
    cloud = FakeCloud()
    lines: list[str] = []
    result = run_setup(_live(cloud, lines), _cfg(), emit=lines.append)
    log = "\n".join(lines)
    assert "token-for-" not in log
    assert result.backend_client_secret not in log
    # トークンは Authorization ヘッダーにだけ載り、Graph と ARM で別の宛先のもの
    assert cloud.auth_headers == {
        "Bearer token-for-https://graph.microsoft.com",
        "Bearer token-for-https://management.azure.com",
    }
    # シークレットは .env 用の行にだけ出る
    assert f"BACKEND_CLIENT_SECRET={result.backend_client_secret}" in env_lines(result)


def test_skip_foundry_roles_makes_no_arm_calls():
    cloud = FakeCloud()
    run_setup(_live(cloud), _cfg(skip_foundry_roles=True), emit=lambda _m: None)
    assert not cloud.role_definitions and not cloud.role_assignments


def test_foundry_roles_need_resource_group_and_account():
    with pytest.raises(ValueError, match="--resource-group"):
        run_setup(DryRunApi(emit=lambda _m: None), _cfg(resource_group=None), emit=lambda _m: None)
