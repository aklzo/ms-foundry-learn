"""部品をまたぐ結合テスト(オフライン): 利用者 → 中間層 → hosted agent → ツールサーバー。

実物のまま動かす部品:
- 中間層バックエンド(FastAPI。利用者トークンの検証 → OBO → ヘッダー 3 つ)
- hosted agent の Responses ハンドラー(Agent Server SDK。ツールの疎通確認と絞り込み・MAF Agent)
- ツールサーバー(MCP 3 つ)と、方式 A では APIM ポリシー(infra/apim/policies/*.xml)のエミュレーター

置き換える部品: Entra ID(``FakeEntra``)とモデル(``ScriptedChatClient``)と Foundry の
ゲートウェイ(ローカルモード: 中間層がエージェントを直接呼ぶので ``Authorization`` は付かない)。

同じ質問を「一般社員」と「経理担当」で流し、判定点が APIM でも MCP サーバーでも、エージェントに
できることが利用者の権限どおりに変わることを確かめる。
"""

from __future__ import annotations

import json

import httpx
import pytest

pytest.importorskip("azure.ai.agentserver.responses")

from azure.ai.agentserver.responses import InMemoryResponseProvider

from delegated_access_maf.agent.host import build_host
from delegated_access_maf.agent.middleware import InMemoryAuditSink
from delegated_access_maf.agent.runtime import DelegatedAccessRuntime
from delegated_access_maf.agent.settings import AgentSettings
from delegated_access_maf.backend.agent_client import HttpAgentClient
from delegated_access_maf.backend.app import create_app
from delegated_access_maf.backend.obo import FakeEntraOboExchanger
from delegated_access_maf.backend.settings import BackendSettings
from delegated_access_maf.contracts import (
    BACKEND_API_SCOPE_NAME,
    BASELINE_DOC_ROLE,
    TOOLS_TOKEN_HEADER,
    USER_IDENTITY_HEADER,
)
from delegated_access_maf.devtools.fake_entra import USERS, FakeEntra
from delegated_access_maf.jwt_validation import JwtValidator
from delegated_access_maf.tools_server.docs_search import InMemoryDocs
from delegated_access_maf.tools_server.offline import offline_tools_server
from delegated_access_maf.tools_server.settings import DEFAULT_DOCS_DIR
from tests.caller_fakes import (
    ModelCall,
    ScriptedChatClient,
    last_tool_result,
    text_reply,
    tool_call_reply,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

AGENT_URL = "http://127.0.0.1:8088/responses"  # ループバック = ローカルモード(Foundry を通らない)
MODES = ["server", "apim"]


class RecordingAgentClient(HttpAgentClient):
    """中間層がエージェントへ送ったヘッダーを記録する(検証用)。"""

    def __init__(self, http: httpx.AsyncClient, url: str) -> None:
        super().__init__(http, url)
        self.sent_headers: list[dict[str, str]] = []

    async def create_response(self, *, headers, body):  # type: ignore[override]
        self.sent_headers.append({k.lower(): v for k, v in headers.items()})
        return await super().create_response(headers=headers, body=body)


class Stack:
    """1 テスト分の部品一式。``chat`` の台本はテストごとに差し替える。"""

    def __init__(self, entra: FakeEntra, tools, chat: ScriptedChatClient, *, mfa: bool = False):
        self.entra = entra
        self.tools = tools
        self.chat = chat
        self.audit = InMemoryAuditSink()
        runtime = DelegatedAccessRuntime(
            chat_client=chat,
            settings=AgentSettings(tools_base_url=tools.base_url),
            transport_factory=lambda: tools.transport,
            audit=self.audit,
        )
        host = build_host(runtime, store=InMemoryResponseProvider(), configure_observability=None)
        self._agent_http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=host), follow_redirects=False
        )
        self.agent = RecordingAgentClient(self._agent_http, AGENT_URL)
        self._jwks_http = httpx.AsyncClient(transport=entra.mock_transport())
        self.obo = FakeEntraOboExchanger(entra, require_mfa=mfa)
        backend = create_app(
            BackendSettings(
                tenant_id=entra.tenant_id,
                backend_api_client_id=entra.backend_client_id,
                tools_api_scope=entra.tools_scope,
                agent_responses_url=AGENT_URL,
            ),
            validator=JwtValidator(
                tenant_id=entra.tenant_id,
                audience=entra.backend_client_id,
                http_client=self._jwks_http,
                required_scope=BACKEND_API_SCOPE_NAME,
            ),
            obo=self.obo,
            foundry_token=None,
            agent_client=self.agent,
        )
        self._backend_http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=backend), base_url="http://backend"
        )

    async def ask(self, alias: str, message: str, **headers: str) -> httpx.Response:
        token = self.entra.issue_user_token(alias)
        return await self._backend_http.post(
            "/chat",
            json={"message": message},
            headers={"Authorization": f"Bearer {token}", **headers},
        )

    async def aclose(self) -> None:
        for client in (self._backend_http, self._agent_http, self._jwks_http):
            await client.aclose()


def update_script(supplier_id: str, days: int):
    """更新ツールが見えていれば呼び、見えていなければ「権限がない」と答える台本。"""

    def script(index: int, call: ModelCall):
        if index == 0 and "update_payment_terms" in call.tool_names:
            return tool_call_reply(
                ("update_payment_terms", {"supplier_id": supplier_id, "days": days})
            )
        if index == 0:
            return text_reply("支払条件を変更するツールが使えないため、更新できません。")
        return text_reply(f"更新しました: {last_tool_result(call)}")

    return script


def search_script(query: str):
    def script(index: int, call: ModelCall):
        if index == 0:
            return tool_call_reply(("search_documents", {"query": query, "top": 5}))
        return text_reply(last_tool_result(call))

    return script


# --- 1. 更新系: 経理担当だけが実行でき、監査に本人の oid が残る -------------------------------


@pytest.mark.parametrize("mode", MODES)
async def test_finance_can_update_payment_terms_and_is_audited(mode) -> None:
    entra = FakeEntra()
    async with offline_tools_server(entra, enforcement=mode) as tools:
        stack = Stack(entra, tools, ScriptedChatClient(update_script("S-1002", 45)))
        try:
            response = await stack.ask("finance", "東和ロジスティクスの支払サイトを 45 日にして")
        finally:
            await stack.aclose()

        body = response.json()
        assert response.status_code == 200, body
        assert body["visible_servers"] == ["docs", "suppliers", "supplier-admin"]
        assert body["hidden_servers"] == []
        assert tools.suppliers.get("S-1002").payment_terms_days == 45
        [record] = tools.suppliers.audit_log
        assert (record.oid, record.before, record.after) == (USERS["finance"].oid, 30, 45)


@pytest.mark.parametrize("mode", MODES)
async def test_employee_never_sees_or_runs_the_update_tool(mode) -> None:
    entra = FakeEntra()
    async with offline_tools_server(entra, enforcement=mode) as tools:
        chat = ScriptedChatClient(update_script("S-1002", 45))
        stack = Stack(entra, tools, chat)
        try:
            response = await stack.ask("employee", "東和ロジスティクスの支払サイトを 45 日にして")
        finally:
            await stack.aclose()

        body = response.json()
        assert response.status_code == 200, body
        assert body["hidden_servers"] == ["supplier-admin"]
        # モデルには更新ツール自体が渡っていない(事前絞り込み)
        assert "update_payment_terms" not in chat.calls[0].tool_names
        assert {"search_documents", "list_suppliers", "get_supplier"} <= set(
            chat.calls[0].tool_names
        )
        # 基幹データは変わらず、監査も空
        assert tools.suppliers.get("S-1002").payment_terms_days == 30
        assert tools.suppliers.audit_log == []


# --- 2. 社内文書: 同じ質問でも、見える文書が利用者のロールで変わる -----------------------------


def result_ids(answer: str) -> set[str]:
    """台本はツール結果(JSON)をそのまま答えるので、結果に含まれた文書 ID を取り出す。"""
    return {hit["id"] for hit in json.loads(answer)["results"]}


@pytest.mark.parametrize("mode", MODES)
async def test_document_trimming_differs_by_user(mode) -> None:
    entra = FakeEntra()
    finance_only = {
        doc.id
        for doc in InMemoryDocs.from_dir(DEFAULT_DOCS_DIR).documents
        if BASELINE_DOC_ROLE not in doc.allowed_roles
    }
    assert finance_only, "テストデータに経理向けだけの文書が必要"
    seen: dict[str, set[str]] = {}
    async with offline_tools_server(entra, enforcement=mode) as tools:
        for alias in ("employee", "finance"):
            stack = Stack(entra, tools, ScriptedChatClient(search_script("与信限度額")))
            try:
                response = await stack.ask(alias, "与信限度額の決め方を教えて")
            finally:
                await stack.aclose()
            assert response.status_code == 200, response.text
            seen[alias] = result_ids(response.json()["answer"])

    assert seen["finance"] & finance_only  # 経理担当には経理向けの文書が出る
    assert not (seen["employee"] & finance_only)  # 一般社員には 1 件も出ない(件数も漏らさない)


# --- 3. 利用者の文脈: 中間層が送る 3 ヘッダーは検証済みトークン由来 ------------------------------


@pytest.mark.parametrize("mode", MODES)
async def test_identity_header_comes_from_validated_token_not_the_client(mode) -> None:
    entra = FakeEntra()
    async with offline_tools_server(entra, enforcement=mode) as tools:
        stack = Stack(entra, tools, ScriptedChatClient([text_reply("こんにちは")]))
        try:
            # 一般社員が経理担当の oid を名乗っても、送られるのは本人の oid
            response = await stack.ask(
                "employee",
                "こんにちは",
                **{USER_IDENTITY_HEADER: USERS["finance"].oid, TOOLS_TOKEN_HEADER: "forged"},
            )
        finally:
            await stack.aclose()

    assert response.status_code == 200, response.text
    [sent] = stack.agent.sent_headers
    assert sent[USER_IDENTITY_HEADER] == USERS["employee"].oid
    assert sent[TOOLS_TOKEN_HEADER] != "forged"
    assert (
        "authorization" not in sent
    )  # ローカルモード(Foundry を通さない)ではワークロードトークンなし


# --- 4. 追加認証(条件付きアクセス)は利用者へ返し、エージェントも MCP も呼ばない ------------------


@pytest.mark.parametrize("mode", MODES)
async def test_claims_challenge_stops_before_agent_and_tools(mode) -> None:
    entra = FakeEntra()
    async with offline_tools_server(entra, enforcement=mode) as tools:
        chat = ScriptedChatClient([text_reply("呼ばれないはず")])
        stack = Stack(entra, tools, chat, mfa=True)
        try:
            response = await stack.ask("finance", "支払サイトを変更して")
        finally:
            await stack.aclose()

        assert response.status_code == 401
        assert 'error="insufficient_claims"' in response.headers["www-authenticate"]
        assert stack.agent.sent_headers == []
        assert chat.calls == []
        assert tools.server.state.auth_decisions.items() == []


# --- 5. トークンの露出: モデルにもエージェントの応答にも委任トークンが出ない -----------------------


@pytest.mark.parametrize("mode", MODES)
async def test_delegated_token_never_reaches_model_or_answer(mode) -> None:
    entra = FakeEntra()
    async with offline_tools_server(entra, enforcement=mode) as tools:
        chat = ScriptedChatClient(update_script("S-1004", 60))
        stack = Stack(entra, tools, chat)
        try:
            response = await stack.ask("finance", "グリーンオフィスの支払サイトを 60 日にして")
        finally:
            await stack.aclose()

    assert response.status_code == 200, response.text
    [sent] = stack.agent.sent_headers
    token = sent[TOOLS_TOKEN_HEADER]
    model_text = "\n".join(call.all_text() for call in chat.calls)
    assert token not in model_text
    assert token.split(".")[1] not in model_text  # JWT の本体部分も
    assert token not in json.dumps(response.json(), ensure_ascii=False)
