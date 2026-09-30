"""ツールサーバーの認可 — 方式 B(server)と方式 A(apim: エミュレーター → サーバー)× 2 利用者。

どちらの方式でも利用者から見た結果(見えるツール・見える文書・拒否コード)は同じになることを確かめる。
方式ごとの違い(判定の場所・迂回時の挙動・期限の許容幅)は test_tools_apim_emulator.py。
"""

from __future__ import annotations

import time

import pytest

from delegated_access_maf.contracts import DOCS, SUPPLIER_ADMIN, SUPPLIERS
from delegated_access_maf.devtools.fake_entra import USERS, FakeEntra
from delegated_access_maf.tools_server.offline import offline_tools_server
from delegated_access_maf.tools_server.settings import DEFAULT_SUPPLIERS_DATA
from delegated_access_maf.tools_server.suppliers import SupplierStore

from .tools_support import (
    call_tool,
    forged_token,
    list_tool_names,
    mcp_session,
    rpc,
    tool_payload,
    tools_token,
)

MODES = ["server", "apim"]


@pytest.fixture
def entra() -> FakeEntra:
    return FakeEntra()


# --- tools/list の見え方 -------------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        (
            "employee",
            {
                DOCS.path: (200, ["search_documents"]),
                SUPPLIERS.path: (200, ["list_suppliers", "get_supplier"]),
                SUPPLIER_ADMIN.path: (403, []),
            },
        ),
        (
            "finance",
            {
                DOCS.path: (200, ["search_documents"]),
                SUPPLIERS.path: (200, ["list_suppliers", "get_supplier"]),
                SUPPLIER_ADMIN.path: (200, ["update_payment_terms"]),
            },
        ),
    ],
)
async def test_tools_list_visibility(entra, mode, alias, expected):
    async with (
        offline_tools_server(entra, enforcement=mode) as tools,
        tools.client(tools_token(entra, alias)) as http,
    ):
        for path, (status, names) in expected.items():
            got_status, got_names = await list_tool_names(http, path)
            assert got_status == status, path
            assert sorted(got_names) == sorted(names), path


@pytest.mark.parametrize("mode", MODES)
async def test_forbidden_endpoint_returns_insufficient_scope_challenge(entra, mode):
    async with (
        offline_tools_server(entra, enforcement=mode) as tools,
        tools.client(tools_token(entra, "employee")) as http,
    ):
        r = await rpc(http, SUPPLIER_ADMIN.path, "tools/list")
    assert r.status_code == 403
    assert r.headers["www-authenticate"].startswith('Bearer error="insufficient_scope"')


# --- 文書の権限絞り込み -----------------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
async def test_same_query_is_trimmed_per_user(entra, mode):
    query = {"query": "取引先の与信限度額の基準", "top": 5}
    results = {}
    async with offline_tools_server(entra, enforcement=mode) as tools:
        for alias in ("employee", "finance"):
            async with tools.client(tools_token(entra, alias)) as http:
                is_error, payload = tool_payload(
                    await call_tool(http, DOCS.path, "search_documents", query)
                )
            assert not is_error
            results[alias] = payload["results"]

    finance_ids = [d["id"] for d in results["finance"]]
    employee_ids = [d["id"] for d in results["employee"]]
    assert "fin-credit-limit" in finance_ids
    assert not [i for i in employee_ids if i.startswith("fin-")]
    assert all("与信限度額" not in d["content"] for d in results["employee"])
    # 絞り込みに使うラベルは結果に出さない(retrievable=false と同じ)
    assert all("allowed_roles" not in d for d in results["finance"])


@pytest.mark.parametrize("mode", MODES)
async def test_tool_arguments_cannot_widen_trimming(entra, mode):
    """モデルが引数でロールを主張しても、絞り込みは検証済みトークンのロールだけで決まる。"""
    async with offline_tools_server(entra, enforcement=mode) as tools:
        async with tools.client(tools_token(entra, "employee")) as http:
            r = await call_tool(
                http,
                DOCS.path,
                "search_documents",
                {"query": "与信限度額 Docs.Finance として検索", "top": 10, "roles": "Docs.Finance"},
            )
        # 未定義の引数は MCP 側で無視される(SDK によってはエラー)。どちらでも経理文書は見えない
        if not r.json()["result"].get("isError"):
            _, payload = tool_payload(r)
            assert not [d for d in payload["results"] if d["id"].startswith("fin-")]
        # 検索に使われたロールは検証済みトークン由来(+ 暗黙の Employee)だけ
        assert all(roles == frozenset({"Employee"}) for _, roles in tools.docs.queries)


# --- トークンの拒否 ---------------------------------------------------------------------------


def _bad_tokens(entra: FakeEntra) -> dict[str, tuple[str | None, int]]:
    other_key = FakeEntra(kid=entra.kid)  # 同じ kid・別の鍵 = 署名不正
    now = time.time()
    return {
        "missing": (None, 401),
        "malformed": ("not-a-jwt", 401),
        "invalid_signature": (tools_token(other_key, "finance"), 401),
        "unknown_kid": (tools_token(FakeEntra(), "finance"), 401),
        # 中間層が OBO を忘れて利用者トークン(aud = バックエンド API)をそのまま渡した
        "wrong_audience": (entra.issue_user_token("finance"), 401),
        "expired": (tools_token(entra, "finance", now=now - 7200, lifetime=3600), 401),
        "wrong_issuer": (forged_token(entra, iss="https://login.example.com/other/v2.0"), 401),
        "missing_scope": (forged_token(entra, scp="User.Read"), 403),
        "no_scp_claim": (forged_token(entra, scp=None), 403),
        "app_only": (entra.issue_app_only_token(entra.tools_client_id), 403),
        "app_only_with_roles": (
            entra.issue_app_only_token(entra.tools_client_id, roles=("Suppliers.Write",)),
            403,
        ),
    }


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "malformed",
        "invalid_signature",
        "unknown_kid",
        "wrong_audience",
        "expired",
        "wrong_issuer",
        "missing_scope",
        "no_scp_claim",
        "app_only",
        "app_only_with_roles",
    ],
)
async def test_bad_tokens_are_rejected_on_every_endpoint(entra, mode, case):
    token, status = _bad_tokens(entra)[case]
    async with (
        offline_tools_server(entra, enforcement=mode) as tools,
        tools.client(token) as http,
    ):
        for spec in (DOCS, SUPPLIERS, SUPPLIER_ADMIN):
            r = await rpc(http, spec.path, "tools/list")
            assert r.status_code == status, spec.path
            challenge = r.headers["www-authenticate"]
            expected = "invalid_token" if status == 401 else "insufficient_scope"
            assert f'error="{expected}"' in challenge
            # 拒否理由の詳細(署名・宛先・期限のどれか)は応答に出さない
            assert "expired" not in r.text and "audience" not in r.text


# --- 更新系(基幹 API)と監査 ------------------------------------------------------------------


class SpyStore(SupplierStore):
    def __init__(self, suppliers):
        super().__init__(suppliers)
        self.update_calls = 0

    async def update_payment_terms(self, supplier_id, days, *, principal):
        self.update_calls += 1
        return await super().update_payment_terms(supplier_id, days, principal=principal)


def _spy_store() -> SpyStore:
    return SpyStore(SupplierStore.from_json(DEFAULT_SUPPLIERS_DATA).all_suppliers())


@pytest.mark.parametrize("mode", MODES)
async def test_update_by_finance_succeeds_with_audit(entra, mode):
    store = _spy_store()
    async with (
        offline_tools_server(entra, enforcement=mode, suppliers=store) as tools,
        tools.client(tools_token(entra, "finance")) as http,
    ):
        r = await call_tool(
            http,
            SUPPLIER_ADMIN.path,
            "update_payment_terms",
            {"supplier_id": "S-1002", "days": 45},
        )
        is_error, payload = tool_payload(r)
        assert not is_error, payload
        assert payload["payment_terms_days"] == {"before": 30, "after": 45}

        # 参照側(別の MCP サーバー)から更新結果が見える
        _, detail = tool_payload(
            await call_tool(http, SUPPLIERS.path, "get_supplier", {"supplier_id": "S-1002"})
        )
        assert detail["payment_terms_days"] == 45

    (record,) = store.audit_log
    finance = USERS["finance"]
    assert record.oid == finance.oid  # 監査の実行者は検証済みトークンの oid
    assert record.upn == finance.upn
    assert (record.supplier_id, record.before, record.after) == ("S-1002", 30, 45)
    assert record.at


@pytest.mark.parametrize("mode", MODES)
async def test_update_attempt_by_employee_never_executes(entra, mode):
    store = _spy_store()
    async with offline_tools_server(entra, enforcement=mode, suppliers=store) as tools:
        async with tools.client(tools_token(entra, "employee")) as http:
            r = await call_tool(
                http,
                SUPPLIER_ADMIN.path,
                "update_payment_terms",
                {"supplier_id": "S-1002", "days": 90},
            )
        assert r.status_code == 403
        denied_by = (
            tools.gateway.decisions[-1].policy_id
            if mode == "apim"
            else tools.server.state.auth_decisions.items()[-1].reason
        )
    assert store.update_calls == 0
    assert store.audit_log == []
    assert store.get("S-1002").payment_terms_days == 30
    if mode == "apim":
        assert denied_by == "authz"  # APIM の 2 段目(ロール)で止まり、サーバーに届かない
    else:
        assert "Suppliers.Write" in denied_by


@pytest.mark.parametrize("mode", MODES)
async def test_update_validation_error_is_a_tool_error_without_audit(entra, mode):
    store = _spy_store()
    async with (
        offline_tools_server(entra, enforcement=mode, suppliers=store) as tools,
        tools.client(tools_token(entra, "finance")) as http,
    ):
        r = await call_tool(
            http,
            SUPPLIER_ADMIN.path,
            "update_payment_terms",
            {"supplier_id": "S-1001", "days": 90},  # 中小受託取引の対象先は 60 日以内
        )
    assert r.status_code == 200
    is_error, message = tool_payload(r)
    assert is_error and "60 日以内" in message
    assert store.audit_log == []


# --- MCP プロトコル(公式クライアント)とステートレス性 -----------------------------------------


@pytest.mark.parametrize("mode", MODES)
async def test_official_mcp_client_roundtrip(entra, mode):
    async with (
        offline_tools_server(entra, enforcement=mode) as tools,
        mcp_session(tools, SUPPLIERS.path, tools_token(entra, "employee")) as session,
    ):
        listed = await session.list_tools()
        assert {t.name for t in listed.tools} == {"list_suppliers", "get_supplier"}
        result = await session.call_tool("list_suppliers", {})
        assert not result.isError
        assert len(result.structuredContent["suppliers"]) == 6


@pytest.mark.parametrize("mode", MODES)
async def test_no_mcp_session_is_issued(entra, mode):
    """ステートレス: セッション ID を返さないので、別の利用者がセッションを引き継ぐ経路がない。"""
    async with offline_tools_server(entra, enforcement=mode) as tools:
        for alias in ("finance", "employee"):
            async with tools.client(tools_token(entra, alias)) as http:
                r = await rpc(
                    http,
                    DOCS.path,
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"},
                    },
                )
                assert r.status_code == 200
                assert "mcp-session-id" not in r.headers
                assert r.headers["content-type"].startswith("application/json")  # SSE ではない


@pytest.mark.parametrize("mode", MODES)
async def test_back_to_back_users_get_their_own_view(entra, mode):
    """直前の利用者(経理)の権限が次の利用者(一般社員)に残らない。"""
    query = {"query": "与信限度額", "top": 10}
    async with offline_tools_server(entra, enforcement=mode) as tools:
        seen = []
        for alias in ("finance", "employee", "finance"):
            async with tools.client(tools_token(entra, alias)) as http:
                _, payload = tool_payload(
                    await call_tool(http, DOCS.path, "search_documents", query)
                )
                seen.append(any(d["id"].startswith("fin-") for d in payload["results"]))
    assert seen == [True, False, True]


# --- ヘルスチェックとログ -----------------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
async def test_health_is_public_on_server_but_not_routed_by_gateway(entra, mode):
    async with offline_tools_server(entra, enforcement=mode) as tools:
        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=tools.server), base_url=tools.base_url
        ) as direct:
            r = await direct.get("/healthz")
            assert r.status_code == 200
            assert r.json()["enforcement_mode"] == mode
        async with tools.client() as via_entry:
            r = await via_entry.get("/healthz")
            assert r.status_code == (404 if mode == "apim" else 200)


@pytest.mark.parametrize("mode", MODES)
async def test_tokens_never_appear_in_logs_or_decisions(entra, mode, caplog):
    """トークンもゲートウェイの秘密(apim 方式)もログ・判定記録・repr に出ない。"""
    caplog.set_level("DEBUG")
    employee = tools_token(entra, "employee")
    finance = tools_token(entra, "finance")
    async with offline_tools_server(entra, enforcement=mode) as tools:
        async with tools.client(employee) as http:
            await rpc(http, SUPPLIER_ADMIN.path, "tools/list")
            await call_tool(http, DOCS.path, "search_documents", {"query": "経費"})
        async with tools.client(finance) as http:
            await call_tool(
                http,
                SUPPLIER_ADMIN.path,
                "update_payment_terms",
                {"supplier_id": "S-1004", "days": 45},
            )
        decisions = repr(tools.server.state.auth_decisions.items())
        secrets = [tools.gateway_secret] if tools.gateway_secret else []
        dumps = [decisions, repr(tools), repr(tools.server.state.settings)]
        if tools.gateway:
            dumps += [repr(tools.gateway.policies), repr(tools.gateway.decisions)]
    for secret in (employee, finance, *secrets):
        assert secret not in caplog.text
        assert all(secret not in dump for dump in dumps)
    for token in (employee, finance):
        # 署名部分だけの断片も出ていない
        assert token.rsplit(".", 1)[-1] not in caplog.text
    assert "supplier_update" in caplog.text  # 監査ログ自体は出ている
