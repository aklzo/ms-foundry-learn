"""APIM ポリシー(infra/apim/policies/*.xml)そのもののテストと、方式 A / B の違いの記録。

エミュレーターは XML から宛先・発行者・必須クレームを読むので、ここでは
(1) 実ファイルが期待どおりの判定を含むこと (2) ファイルを書き換えると判定が変わること
(3) 解釈できない書き方は黙って無視せず失敗すること を確かめる。
"""

from __future__ import annotations

import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from delegated_access_maf.contracts import (
    APIM_GATEWAY_SECRET_HEADER,
    DOCS,
    MCP_SERVERS,
    SUPPLIER_ADMIN,
    SUPPLIERS,
)
from delegated_access_maf.devtools.fake_entra import USERS, FakeEntra
from delegated_access_maf.tools_server.apim_emulator import (
    ApimEmulator,
    SetHeader,
    UnsupportedPolicyError,
    ValidateJwt,
    load_policies,
    named_values_for,
    parse_policy,
)
from delegated_access_maf.tools_server.app import create_app, make_validator
from delegated_access_maf.tools_server.docs_search import InMemoryDocs
from delegated_access_maf.tools_server.offline import offline_tools_server
from delegated_access_maf.tools_server.settings import (
    DEFAULT_DOCS_DIR,
    DEFAULT_POLICIES_DIR,
    DEFAULT_SUPPLIERS_DATA,
    ToolsServerSettings,
)
from delegated_access_maf.tools_server.suppliers import SupplierStore

from .tools_support import call_tool, forged_token, list_tool_names, rpc, tool_payload, tools_token

SECRET = "test-gateway-secret-0123456789abcdef"


@pytest.fixture
def entra() -> FakeEntra:
    return FakeEntra()


@pytest.fixture
def named(entra) -> dict[str, str]:
    return named_values_for(entra.tenant_id, entra.tools_client_id, SECRET)


# --- 実ファイルの内容 ---------------------------------------------------------------------------


def test_policy_files_exist_for_every_mcp_server():
    names = sorted(p.stem for p in DEFAULT_POLICIES_DIR.glob("*.xml"))
    assert names == sorted(s.name for s in MCP_SERVERS)


def test_policies_validate_token_then_authorize(entra, named):
    policies = load_policies(named)
    issuer = f"https://login.microsoftonline.com/{entra.tenant_id}/v2.0"
    for spec in MCP_SERVERS:
        token_step, authz_step, secret_step = policies[spec.name].inbound  # この順で実行される
        assert isinstance(token_step, ValidateJwt) and isinstance(authz_step, ValidateJwt)
        # 3 つ目: 判定を通った要求にだけ、秘密の Named Value をゲートウェイの証明として付ける
        assert isinstance(secret_step, SetHeader)
        assert (secret_step.name, secret_step.exists_action) == (
            APIM_GATEWAY_SECRET_HEADER,
            "override",  # 利用者が同名ヘッダーを送っても上書き
        )
        assert secret_step.value == SECRET
        assert SECRET not in repr(policies[spec.name])  # 秘密は repr に出さない
        for step in (token_step, authz_step):
            assert step.audiences == (entra.tools_client_id,)
            assert step.issuers == (issuer,)
            assert step.openid_config_urls == (f"{issuer}/.well-known/openid-configuration",)
            assert step.header_name == "Authorization" and step.require_scheme == "Bearer"
        assert (token_step.id, token_step.failed_status, token_step.required_claims) == (
            "token",
            401,
            (),
        )
        assert (authz_step.id, authz_step.failed_status) == ("authz", 403)
        claims = {c.name: c for c in authz_step.required_claims}
        assert claims["scp"].values == ("Tools.Access",) and claims["scp"].separator == " "
        # ロールの要件は契約(contracts.McpServerSpec.required_roles)と一致していること
        roles = set(claims["roles"].values) if "roles" in claims else set()
        assert roles == set(spec.required_roles), spec.name
        # on-error で両方の失敗に WWW-Authenticate を付ける
        assert {r.policy_id for r in policies[spec.name].on_error} == {"token", "authz"}


def test_missing_named_value_fails_loudly(entra):
    with pytest.raises(UnsupportedPolicyError, match="dah-tools-api-client-id"):
        load_policies({"dah-tenant-id": entra.tenant_id})
    with pytest.raises(UnsupportedPolicyError, match="dah-gateway-secret"):
        load_policies(
            {"dah-tenant-id": entra.tenant_id, "dah-tools-api-client-id": entra.tools_client_id}
        )


@pytest.mark.parametrize(
    "snippet",
    [
        '<inbound><base /><rate-limit calls="5" renewal-period="30" /></inbound>',
        (
            '<inbound><validate-jwt header-name="Authorization" failed-validation-httpcode="@(401)">'
            '<openid-config url="https://x" /></validate-jwt></inbound>'
        ),
        (
            '<inbound><validate-jwt header-name="Authorization"><issuer-signing-keys>'
            "<key>abc</key></issuer-signing-keys></validate-jwt></inbound>"
        ),
        (
            '<inbound><validate-jwt token-value="@(x)"><openid-config url="https://x" />'
            "</validate-jwt></inbound>"
        ),
        "<outbound><set-body>@(context.Response.Body.As&lt;string&gt;())</set-body></outbound>",
        (
            '<inbound><set-header name="x-apim-gateway-secret" exists-action="override">'
            '<value>@(context.Request.Headers.GetValueOrDefault("x"))</value></set-header></inbound>'
        ),
        (
            '<inbound><set-header name="x-apim-gateway-secret" exists-action="append">'
            "<value>v</value></set-header></inbound>"
        ),
        (
            "<on-error><choose><when condition='@(context.Response.StatusCode == 401)'>"
            '<set-header name="X" exists-action="override"><value>v</value></set-header>'
            "</when></choose></on-error>"
        ),
    ],
)
def test_unsupported_policy_is_rejected_not_ignored(snippet):
    with pytest.raises(UnsupportedPolicyError):
        parse_policy(f"<policies>{snippet}</policies>", name="x", named_values={})


# --- ファイルを書き換えると判定が変わる(= ファイルが判定の正本)---------------------------------


def _copy_policies(tmp_path: Path) -> Path:
    target = tmp_path / "policies"
    shutil.copytree(DEFAULT_POLICIES_DIR, target)
    return target


@asynccontextmanager
async def _gateway(entra, named, policies_dir, token, *, server_secret=SECRET):
    """指定したポリシーファイルで疑似 APIM → ツールサーバー(apim 方式)を組み立てる。"""
    settings = ToolsServerSettings(
        tenant_id=entra.tenant_id,
        tools_client_id=entra.tools_client_id,
        enforcement_mode="apim",
        apim_gateway_secret=server_secret,
    )
    async with httpx.AsyncClient(transport=entra.mock_transport()) as jwks:
        server = create_app(
            settings,
            validator=make_validator(settings, http_client=jwks),
            docs=InMemoryDocs.from_dir(DEFAULT_DOCS_DIR),
            suppliers=SupplierStore.from_json(DEFAULT_SUPPLIERS_DATA),
        )
        gateway = ApimEmulator(
            server, named_values=named, http_client=jwks, policies_dir=policies_dir
        )
        async with (
            server.router.lifespan_context(server),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=gateway),
                base_url="http://apim.test",
                headers={"Authorization": f"Bearer {token}"},
            ) as http,
        ):
            yield http, server


async def _gateway_statuses(entra, named, policies_dir, alias):
    async with _gateway(entra, named, policies_dir, tools_token(entra, alias)) as (http, _):
        return {spec.name: (await list_tool_names(http, spec.path))[0] for spec in MCP_SERVERS}


async def test_real_policy_files_drive_the_decision(entra, named):
    statuses = await _gateway_statuses(entra, named, DEFAULT_POLICIES_DIR, "employee")
    assert statuses == {"docs": 200, "suppliers": 200, "supplier-admin": 403}


async def test_removing_role_claim_from_xml_opens_supplier_admin(entra, named, tmp_path):
    policies_dir = _copy_policies(tmp_path)
    path = policies_dir / "supplier-admin.xml"
    xml = path.read_text(encoding="utf-8")
    start = xml.index('<claim name="roles"')
    end = xml.index("</claim>", start) + len("</claim>")
    path.write_text(xml[:start] + xml[end:], encoding="utf-8")

    statuses = await _gateway_statuses(entra, named, policies_dir, "employee")
    assert statuses["supplier-admin"] == 200  # ポリシーの 1 行が一般社員の更新可否を決めている


async def test_changing_audience_in_xml_rejects_valid_tokens(entra, tmp_path):
    policies_dir = _copy_policies(tmp_path)
    named = named_values_for(entra.tenant_id, "33333333-3333-3333-3333-333333333333", SECRET)
    statuses = await _gateway_statuses(entra, named, policies_dir, "finance")
    assert set(statuses.values()) == {401}


async def test_removing_set_header_from_xml_makes_server_refuse(entra, named, tmp_path):
    """XML の set-header が秘密を付けなければ、APIM の判定を通ってもサーバーが 403 にする。"""
    policies_dir = _copy_policies(tmp_path)
    path = policies_dir / "docs.xml"
    xml = path.read_text(encoding="utf-8")
    start = xml.index(f'<set-header name="{APIM_GATEWAY_SECRET_HEADER}"')
    end = xml.index("</set-header>", start) + len("</set-header>")
    path.write_text(xml[:start] + xml[end:], encoding="utf-8")

    async with _gateway(entra, named, policies_dir, tools_token(entra, "finance")) as (
        http,
        server,
    ):
        assert (await list_tool_names(http, DOCS.path))[0] == 403
        assert (await list_tool_names(http, SUPPLIERS.path))[0] == 200  # 他の API は元のまま
        reasons = [d.reason for d in server.state.auth_decisions.items()]
    assert reasons == ["gateway_secret_mismatch", "token verified by server; authorization by APIM"]


async def test_gateway_and_server_secrets_must_match(entra, named):
    async with _gateway(
        entra, named, DEFAULT_POLICIES_DIR, tools_token(entra, "finance"), server_secret="other"
    ) as (http, _):
        assert {(await list_tool_names(http, s.path))[0] for s in MCP_SERVERS} == {403}


async def test_client_supplied_secret_header_is_overwritten_by_gateway(entra, named):
    async with _gateway(entra, named, DEFAULT_POLICIES_DIR, tools_token(entra, "finance")) as (
        http,
        server,
    ):
        http.headers[APIM_GATEWAY_SECRET_HEADER] = "attacker-guess"
        assert (await list_tool_names(http, DOCS.path))[0] == 200
        (decision,) = server.state.auth_decisions.items()
    assert decision.decision == "allow"


# --- APIM と同じ形の失敗応答 ----------------------------------------------------------------------


async def test_failure_responses_look_like_apim(entra):
    async with offline_tools_server(entra, enforcement="apim") as tools:
        async with tools.client("garbage") as http:
            r401 = await rpc(http, DOCS.path, "tools/list")
        async with tools.client(tools_token(entra, "employee")) as http:
            r403 = await rpc(http, SUPPLIER_ADMIN.path, "tools/list")
    assert r401.status_code == 401
    assert r401.json() == {
        "statusCode": 401,
        "message": "Unauthorized. The access token is missing or invalid.",
    }
    assert r401.headers["www-authenticate"].startswith('Bearer error="invalid_token"')
    assert r403.status_code == 403
    assert r403.json()["statusCode"] == 403
    assert r403.headers["www-authenticate"].startswith('Bearer error="insufficient_scope"')


async def test_gateway_routes_only_post_to_contract_paths(entra):
    async with offline_tools_server(entra, enforcement="apim") as tools:
        async with tools.client(tools_token(entra, "finance")) as http:
            assert (await http.get(DOCS.path)).status_code == 404
            assert (await rpc(http, "/docs/other", "tools/list")).status_code == 404
            assert (await rpc(http, DOCS.path, "tools/list")).status_code == 200
        forwarded = [d for d in tools.gateway.decisions if d.status == 200]
    assert len(forwarded) == 1


async def test_gateway_forwards_the_user_token_to_the_server(entra):
    """APIM は Authorization をそのまま転送し、サーバーは同じトークンで利用者を特定する。"""
    async with offline_tools_server(entra, enforcement="apim") as tools:
        async with tools.client(tools_token(entra, "finance")) as http:
            await rpc(http, SUPPLIERS.path, "tools/list")
        (decision,) = tools.server.state.auth_decisions.items()
    assert decision.decision == "allow" and decision.upn == "finance@contoso.example"
    assert decision.reason.endswith("authorization by APIM")


# --- 方式 A の迂回(APIM を通さずツールサーバーを直接呼ぶ)---------------------------------------


def _direct(tools, token: str, secret: str | list[str] | None = None) -> httpx.AsyncClient:
    """ゲートウェイを通さずツールサーバー本体を呼ぶクライアント(秘密ヘッダーは任意で付ける)。"""
    headers: list[tuple[str, str]] = [("Authorization", f"Bearer {token}")]
    for value in [secret] if isinstance(secret, str) else secret or []:
        headers.append((APIM_GATEWAY_SECRET_HEADER, value))
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=tools.server), base_url=tools.base_url, headers=headers
    )


@pytest.mark.parametrize("alias", ["employee", "finance"])
@pytest.mark.parametrize("presented", ["missing", "wrong", "duplicated"])
async def test_apim_mode_bypass_without_gateway_secret_is_rejected(entra, alias, presented):
    """APIM を迂回した呼び出しは、正しい利用者トークンを持っていても 403(更新は実行されない)。"""
    async with offline_tools_server(entra, enforcement="apim") as tools:
        secret = {
            "missing": None,
            "wrong": "not-the-secret",
            "duplicated": [tools.gateway_secret, "not-the-secret"],
        }[presented]
        async with _direct(tools, tools_token(entra, alias), secret) as bypass:
            r = await call_tool(
                bypass,
                SUPPLIER_ADMIN.path,
                "update_payment_terms",
                {"supplier_id": "S-1004", "days": 60},
            )
            listed = await rpc(bypass, DOCS.path, "tools/list")
        decisions = tools.server.state.auth_decisions.items()
    assert r.status_code == 403 and listed.status_code == 403
    assert r.json() == {"error": "forbidden"}  # 本文は汎用。理由はログだけ
    assert "www-authenticate" not in r.headers  # トークンの問題ではないので Bearer チャレンジなし
    assert [d.reason for d in decisions] == ["gateway_secret_mismatch"] * 2
    assert all(d.oid is None for d in decisions)  # トークンを見る前に止めている
    assert tools.suppliers.audit_log == []
    assert tools.suppliers.get("S-1004").payment_terms_days == 30


@pytest.mark.parametrize("case", ["forged_signature", "wrong_audience", "expired"])
async def test_apim_mode_server_still_revalidates_tokens_behind_the_secret(entra, case):
    """秘密を知る経路(= APIM)から来ても、署名・宛先・期限はサーバーが再検証する(多層防御)。"""
    token = {
        "forged_signature": tools_token(FakeEntra(kid=entra.kid), "finance"),
        "wrong_audience": entra.issue_user_token("finance"),
        "expired": tools_token(entra, "finance", now=time.time() - 7200, lifetime=3600),
    }[case]
    async with (
        offline_tools_server(entra, enforcement="apim") as tools,
        _direct(tools, token, tools.gateway_secret) as insider,
    ):
        r = await rpc(insider, SUPPLIER_ADMIN.path, "tools/list")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith('Bearer error="invalid_token"')


async def test_leaked_gateway_secret_reopens_the_bypass(entra):
    """残るリスクの記録: 秘密が漏れればロール判定を迂回できる(ロールは APIM でしか見ていない)。

    → 秘密は Named Value(secret)と Container Apps のシークレットで管理し、ログ・トレースに出さない。
      より強い代替は APIM のマネージド ID トークンをサーバーが検証する方式(tools_server/auth.py)。
    """
    async with (
        offline_tools_server(entra, enforcement="apim") as tools,
        _direct(tools, tools_token(entra, "employee"), tools.gateway_secret) as leaked,
    ):
        r = await call_tool(
            leaked,
            SUPPLIER_ADMIN.path,
            "update_payment_terms",
            {"supplier_id": "S-1004", "days": 60},
        )
    assert r.status_code == 200 and not tool_payload(r)[0]
    assert tools.suppliers.audit_log[-1].oid == USERS["employee"].oid


async def test_server_mode_ignores_and_strips_the_gateway_header(entra):
    """server 方式は秘密を要求しない(判定は自分でする)。ヘッダーが来ても MCP へは渡さない。"""
    async with offline_tools_server(entra, enforcement="server") as tools:
        assert tools.gateway_secret is None
        async with _direct(tools, tools_token(entra, "employee"), "whatever") as http:
            assert (await list_tool_names(http, DOCS.path))[0] == 200
            assert (await list_tool_names(http, SUPPLIER_ADMIN.path))[0] == 403


async def test_middleware_removes_secret_before_mcp(entra):
    from delegated_access_maf.tools_server.auth import AuthDecisionLog, McpAuthMiddleware

    seen: list[list[tuple[bytes, bytes]]] = []

    async def inner(scope, receive, send):
        seen.append(list(scope["headers"]))
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    settings = ToolsServerSettings(tenant_id=entra.tenant_id, tools_client_id=entra.tools_client_id)
    async with httpx.AsyncClient(transport=entra.mock_transport()) as jwks:
        guarded = McpAuthMiddleware(
            inner,
            spec=DOCS,
            validator=make_validator(settings, http_client=jwks, enforcement="apim"),
            enforcement="apim",
            decisions=AuthDecisionLog(),
            gateway_secret=SECRET,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=guarded), base_url="http://t"
        ) as http:
            r = await http.post(
                "/mcp",
                headers={
                    "Authorization": f"Bearer {forged_token(entra)}",
                    APIM_GATEWAY_SECRET_HEADER: SECRET,
                },
            )
    assert r.status_code == 204
    (headers,) = seen
    assert APIM_GATEWAY_SECRET_HEADER.encode() not in {name for name, _ in headers}
    assert SECRET.encode() not in {value for _, value in headers}


def test_apim_mode_refuses_to_start_without_secret(entra):
    from delegated_access_maf.tools_server.auth import AuthDecisionLog, McpAuthMiddleware
    from delegated_access_maf.tools_server.settings import SettingsError

    settings = ToolsServerSettings(
        tenant_id=entra.tenant_id, tools_client_id=entra.tools_client_id, enforcement_mode="apim"
    )
    with pytest.raises(SettingsError, match="APIM_GATEWAY_SECRET"):
        create_app(
            settings,
            validator=make_validator(settings, http_client=httpx.AsyncClient()),
            docs=InMemoryDocs([]),
            suppliers=SupplierStore([]),
        )
    with pytest.raises(ValueError, match="gateway secret"):
        McpAuthMiddleware(
            inner_app_never_called,
            spec=DOCS,
            validator=make_validator(settings, http_client=httpx.AsyncClient()),
            enforcement="apim",
            decisions=AuthDecisionLog(),
        )


async def inner_app_never_called(scope, receive, send):  # pragma: no cover
    raise AssertionError("must not be reached")


# --- 方式 A / B の違い(README の比較表の根拠)----------------------------------------------------


async def test_expiry_tolerance_differs_between_modes(entra):
    """期限切れ直後(30 秒)のトークン: APIM は clock-skew 既定 0 秒で拒否、サーバーは 60 秒の猶予で通す。"""
    token = tools_token(entra, "finance", now=time.time() - 3630, lifetime=3600)
    statuses = {}
    for mode in ("server", "apim"):
        async with (
            offline_tools_server(entra, enforcement=mode) as tools,
            tools.client(token) as http,
        ):
            statuses[mode] = (await rpc(http, DOCS.path, "tools/list")).status_code
    assert statuses == {"server": 200, "apim": 401}
