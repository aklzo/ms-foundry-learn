"""中間層バックエンド — 利用者トークンの検証・OBO・hosted agent へのヘッダー 3 つ。

hosted agent は httpx の MockTransport で受け、届いたヘッダーと本文を記録する。
"""

from __future__ import annotations

import base64
import json
import logging

import httpx
import pytest

from delegated_access_maf.agent import signals
from delegated_access_maf.backend.agent_client import HttpAgentClient
from delegated_access_maf.backend.app import create_app
from delegated_access_maf.backend.obo import (
    FakeEntraOboExchanger,
    OboChallenge,
    OboError,
    StaticFoundryToken,
    token_from_msal_result,
)
from delegated_access_maf.backend.settings import BackendSettings, SettingsError
from delegated_access_maf.contracts import (
    BACKEND_API_SCOPE_NAME,
    MSG_REAUTH,
    TOOLS_TOKEN_HEADER,
    USER_IDENTITY_HEADER,
)
from delegated_access_maf.devtools.fake_entra import USERS, FakeEntra
from delegated_access_maf.jwt_validation import JwtValidator
from delegated_access_maf.redaction import RedactingLogFilter

HOSTED_URL = (
    "https://acct.services.ai.azure.com/api/projects/p/agents/delegated-access-agent"
    "/endpoint/protocols/openai/responses?api-version=v1"
)
LOCAL_URL = "http://localhost:8088/responses"
FOUNDRY_TOKEN = "foundry-workload-token-abc123"


class FakeAgent:
    """hosted agent の代役。受け取ったリクエストを記録し、決まった Responses 応答を返す。"""

    def __init__(self, *, status_code: int = 200, body: dict | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.status_code = status_code
        self.body = body or completed("回答です", {signals.META_STATUS: signals.STATUS_OK})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status_code, json=self.body)


def completed(text: str, metadata: dict[str, str], status: str = "completed") -> dict:
    return {
        "id": "caresp_1",
        "object": "response",
        "status": status,
        "metadata": metadata,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


@pytest.fixture
def entra() -> FakeEntra:
    return FakeEntra()


def make_client(
    entra: FakeEntra,
    agent: FakeAgent,
    *,
    agent_url: str = HOSTED_URL,
    require_mfa: bool = False,
    obo: object | None = None,
) -> tuple[httpx.AsyncClient, FakeEntraOboExchanger, StaticFoundryToken]:
    settings = BackendSettings(
        tenant_id=entra.tenant_id,
        backend_api_client_id=entra.backend_client_id,
        tools_api_scope=entra.tools_scope,
        agent_responses_url=agent_url,
    )
    obo = obo or FakeEntraOboExchanger(entra, require_mfa=require_mfa)
    foundry = StaticFoundryToken(FOUNDRY_TOKEN)
    app = create_app(
        settings,
        validator=JwtValidator(
            tenant_id=entra.tenant_id,
            audience=entra.backend_client_id,
            http_client=httpx.AsyncClient(transport=entra.mock_transport()),
            required_scope=BACKEND_API_SCOPE_NAME,
        ),
        obo=obo,
        foundry_token=foundry,
        agent_client=HttpAgentClient(
            httpx.AsyncClient(transport=httpx.MockTransport(agent.handler)), agent_url
        ),
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://backend")
    return client, obo, foundry


async def chat(
    client: httpx.AsyncClient, token: str | None, message: str = "質問", **extra
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    headers.update(extra.pop("headers", {}))
    return await client.post("/chat", json={"message": message, **extra}, headers=headers)


# --- ヘッダー 3 つ -------------------------------------------------------------------------


async def test_agent_receives_exactly_the_three_delegation_headers(entra) -> None:
    agent = FakeAgent()
    client, obo, _ = make_client(entra, agent)
    user_token = entra.issue_user_token("finance")
    response = await chat(client, user_token)

    assert response.status_code == 200
    sent = agent.requests[0].headers
    # Authorization はバックエンド自身の Foundry 用トークンで、利用者のトークンではない
    assert sent["authorization"] == f"Bearer {FOUNDRY_TOKEN}"
    assert user_token not in str(agent.requests[0].headers.raw)
    # 委任トークンは Bearer なしの生値、宛先はツール API
    tools_token = sent[TOOLS_TOKEN_HEADER]
    assert not tools_token.lower().startswith("bearer ")
    claims = json.loads(base64.urlsafe_b64decode(tools_token.split(".")[1] + "=="))
    assert claims["aud"] == entra.tools_client_id
    assert claims["oid"] == USERS["finance"].oid
    # x-ms-user-identity は検証済みトークンの oid(トークンではない)
    assert sent[USER_IDENTITY_HEADER] == USERS["finance"].oid
    custom = {k for k in sent if k.startswith("x-")}
    assert custom == {TOOLS_TOKEN_HEADER, USER_IDENTITY_HEADER}
    assert obo.calls == 1


async def test_spoofed_identity_headers_from_the_client_are_ignored(entra) -> None:
    agent = FakeAgent()
    client, _, _ = make_client(entra, agent)
    response = await chat(
        client,
        entra.issue_user_token("employee"),
        headers={
            USER_IDENTITY_HEADER: USERS["finance"].oid,
            TOOLS_TOKEN_HEADER: "attacker-supplied-token",
            "x-client-user-id": "finance",
        },
    )

    assert response.status_code == 200
    sent = agent.requests[0].headers
    assert sent[USER_IDENTITY_HEADER] == USERS["employee"].oid
    assert sent[TOOLS_TOKEN_HEADER] != "attacker-supplied-token"
    assert "x-client-user-id" not in sent


async def test_request_body_is_foreground_and_carries_previous_response_id(entra) -> None:
    agent = FakeAgent()
    client, _, _ = make_client(entra, agent)
    await chat(
        client, entra.issue_user_token("employee"), "続き", previous_response_id="caresp_prev"
    )

    body = json.loads(agent.requests[0].content)
    assert body == {
        "input": "続き",
        "stream": False,
        "background": False,
        "store": True,
        "previous_response_id": "caresp_prev",
    }


async def test_local_mode_omits_the_foundry_token(entra) -> None:
    agent = FakeAgent()
    client, _, foundry = make_client(entra, agent, agent_url=LOCAL_URL)
    response = await chat(client, entra.issue_user_token("employee"))

    assert response.status_code == 200
    assert "authorization" not in agent.requests[0].headers
    assert foundry.calls == 0
    assert agent.requests[0].headers[USER_IDENTITY_HEADER] == USERS["employee"].oid


# --- 利用者トークンの検証 --------------------------------------------------------------------


async def test_missing_or_invalid_user_token_is_401_without_obo(entra) -> None:
    agent = FakeAgent()
    client, obo, _ = make_client(entra, agent)

    missing = await chat(client, None)
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"].startswith("Bearer")

    forged = await chat(client, FakeEntra().issue_user_token("employee"))  # 別の鍵で署名
    assert forged.status_code == 401
    assert 'error="invalid_token"' in forged.headers["www-authenticate"]

    expired = await chat(client, entra.issue_user_token("employee", now=1_000_000))
    assert expired.status_code == 401

    assert obo.calls == 0 and agent.requests == []


async def test_token_for_another_audience_or_app_only_is_rejected(entra) -> None:
    agent = FakeAgent()
    client, obo, _ = make_client(entra, agent)

    tools_audience = entra.obo_exchange(entra.issue_user_token("finance"), entra.tools_scope)[
        "access_token"
    ]
    assert (await chat(client, tools_audience)).status_code == 401  # aud がツール API

    app_only = entra.issue_app_only_token(entra.backend_client_id)
    response = await chat(client, app_only)  # 利用者なし → OBO の assertion にできない
    assert response.status_code == 403
    assert 'error="insufficient_scope"' in response.headers["www-authenticate"]
    assert obo.calls == 0 and agent.requests == []


# --- OBO の失敗 ----------------------------------------------------------------------------


async def test_claims_challenge_is_returned_to_the_client_and_the_agent_is_not_called(
    entra,
) -> None:
    agent = FakeAgent()
    client, _, foundry = make_client(entra, agent, require_mfa=True)
    response = await chat(client, entra.issue_user_token("finance"))

    assert response.status_code == 401
    challenge = response.headers["www-authenticate"]
    assert 'error="insufficient_claims"' in challenge
    claims_b64 = challenge.split('claims="', 1)[1].split('"', 1)[0]
    assert json.loads(base64.b64decode(claims_b64)) == {
        "access_token": {"acrs": {"essential": True, "value": "c1"}}
    }
    assert response.json()["claims"] == claims_b64
    assert response.json()["message"] == MSG_REAUTH
    # アプリ権限での代替もエージェント呼び出しもしない
    assert agent.requests == [] and foundry.calls == 0


def test_msal_result_interpretation() -> None:
    assert token_from_msal_result({"access_token": "t"}) == "t"
    with pytest.raises(OboChallenge) as challenge:
        token_from_msal_result({"error": "interaction_required", "claims": '{"access_token":{}}'})
    assert base64.b64decode(challenge.value.claims_b64) == b'{"access_token":{}}'
    with pytest.raises(OboError) as reauth:
        token_from_msal_result({"error": "invalid_grant", "suberror": "consent_required"})
    assert reauth.value.reauth
    with pytest.raises(OboError) as config:
        token_from_msal_result({"error": "invalid_client"})
    assert not config.value.reauth


async def test_obo_reauth_error_is_401_and_config_error_is_502(entra) -> None:
    class FailingObo:
        def __init__(self, error: str) -> None:
            self.error = error

        async def exchange(self, user_assertion: str) -> str:
            return token_from_msal_result({"error": self.error})

    for error, expected in (("invalid_grant", 401), ("invalid_client", 502)):
        agent = FakeAgent()
        client, _, _ = make_client(entra, agent, obo=FailingObo(error))
        response = await chat(client, entra.issue_user_token("employee"))
        assert response.status_code == expected, error
        assert agent.requests == []


# --- エージェントの応答 ----------------------------------------------------------------------


async def test_answer_and_visible_tools_are_returned(entra) -> None:
    agent = FakeAgent(
        body=completed(
            "取引先は 2 社です",
            {
                signals.META_STATUS: signals.STATUS_OK,
                signals.META_VISIBLE_SERVERS: "docs,suppliers",
                signals.META_HIDDEN_SERVERS: "supplier-admin",
            },
        )
    )
    client, _, _ = make_client(entra, agent)
    body = (await chat(client, entra.issue_user_token("employee"))).json()

    assert body["answer"] == "取引先は 2 社です"
    assert body["response_id"] == "caresp_1"
    assert body["user"]["oid"] == USERS["employee"].oid
    assert body["visible_servers"] == ["docs", "suppliers"]
    assert body["hidden_servers"] == ["supplier-admin"]


async def test_agent_reauth_signal_becomes_401(entra) -> None:
    agent = FakeAgent(
        body=completed(
            MSG_REAUTH,
            {
                signals.META_STATUS: signals.STATUS_REAUTH,
                signals.META_REASON: signals.REASON_TOOL_UNAUTHORIZED,
            },
        )
    )
    client, _, _ = make_client(entra, agent)
    response = await chat(client, entra.issue_user_token("employee"))

    assert response.status_code == 401
    assert 'error="invalid_token"' in response.headers["www-authenticate"]
    assert response.json()["reason"] == signals.REASON_TOOL_UNAUTHORIZED


async def test_downstream_claims_challenge_is_passed_to_the_client(entra) -> None:
    """MCP サーバー(CAE など)の 401 に claims チャレンジが付いていたら、そのまま利用者へ返す。"""
    claims_b64 = base64.b64encode(b'{"access_token":{"nbf":{"essential":true}}}').decode()
    agent = FakeAgent(
        body=completed(
            MSG_REAUTH,
            {
                signals.META_STATUS: signals.STATUS_REAUTH,
                signals.META_REASON: signals.REASON_TOOL_UNAUTHORIZED,
                signals.META_WWW_AUTHENTICATE: (
                    f'Bearer error="insufficient_claims", claims="{claims_b64}"'
                ),
            },
        )
    )
    client, _, _ = make_client(entra, agent)
    response = await chat(client, entra.issue_user_token("employee"))

    assert response.status_code == 401
    assert f'claims="{claims_b64}"' in response.headers["www-authenticate"]
    assert response.json()["error"] == "insufficient_claims"


@pytest.mark.parametrize(
    ("status_code", "body"),
    [
        (403, {"error": {"code": "forbidden"}}),  # UserIdentityImpersonation が無い
        (200, completed("", {signals.META_STATUS: signals.STATUS_ERROR}, status="failed")),
        (500, {"error": {"code": "server_error"}}),
    ],
)
async def test_agent_failures_are_502(entra, status_code, body) -> None:
    client, _, _ = make_client(entra, FakeAgent(status_code=status_code, body=body))
    response = await chat(client, entra.issue_user_token("employee"))
    assert response.status_code == 502


async def test_tokens_do_not_appear_in_backend_logs(entra, caplog) -> None:
    agent = FakeAgent()
    client, _, _ = make_client(entra, agent)
    caplog.set_level(logging.DEBUG)
    caplog.handler.addFilter(RedactingLogFilter())
    user_token = entra.issue_user_token("finance")
    await chat(client, user_token)
    tools_token = agent.requests[0].headers[TOOLS_TOKEN_HEADER]

    for token in (user_token, tools_token, FOUNDRY_TOKEN):
        assert token.rsplit(".", 1)[-1] not in caplog.text
    assert USERS["finance"].oid in caplog.text  # 誰の要求かは残る


# --- 設定 ------------------------------------------------------------------------------------


def test_settings_from_env() -> None:
    env = {
        "ENTRA_TENANT_ID": "t",
        "BACKEND_API_CLIENT_ID": "b",
        "TOOLS_API_CLIENT_ID": "tools",
        "AGENT_RESPONSES_URL": LOCAL_URL,
    }
    settings = BackendSettings.from_env(env)
    assert settings.tools_api_scope == "api://tools/Tools.Access"
    assert settings.backend_api_scope == "api://b/access_as_user"
    assert settings.local_agent
    assert settings.foundry_scope == "https://ai.azure.com/.default"
    assert not BackendSettings.from_env({**env, "AGENT_RESPONSES_URL": HOSTED_URL}).local_agent
    with pytest.raises(SettingsError):
        BackendSettings.from_env(
            {**env, "AGENT_RESPONSES_URL": "http://agent.example.com/responses"}
        )
    with pytest.raises(SettingsError):
        BackendSettings.from_env({k: v for k, v in env.items() if k != "BACKEND_API_CLIENT_ID"})


def test_hosted_mode_requires_a_foundry_token_provider(entra) -> None:
    settings = BackendSettings(
        tenant_id=entra.tenant_id,
        backend_api_client_id=entra.backend_client_id,
        tools_api_scope=entra.tools_scope,
        agent_responses_url=HOSTED_URL,
    )
    with pytest.raises(ValueError, match="foundry_token"):
        create_app(settings, validator=None, obo=None, foundry_token=None, agent_client=None)  # type: ignore[arg-type]
