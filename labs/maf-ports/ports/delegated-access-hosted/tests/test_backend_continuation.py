"""会話の継続: 他人の会話 ID は Foundry が 404 を返す(ライブで確認)→ 中間層は 404 で返す。"""

from __future__ import annotations

import httpx

from delegated_access_maf.backend.agent_client import AgentReply
from delegated_access_maf.backend.app import MSG_CONVERSATION_NOT_FOUND, create_app
from delegated_access_maf.backend.obo import FakeEntraOboExchanger
from delegated_access_maf.backend.settings import BackendSettings
from delegated_access_maf.contracts import BACKEND_API_SCOPE_NAME
from delegated_access_maf.devtools.fake_entra import FakeEntra
from delegated_access_maf.jwt_validation import JwtValidator


class NotFoundAgent:
    def __init__(self) -> None:
        self.bodies: list[dict] = []

    async def create_response(self, *, headers, body):
        self.bodies.append(body)
        return AgentReply(http_status=404)


async def _chat(body: dict) -> tuple[httpx.Response, NotFoundAgent]:
    entra = FakeEntra()
    agent = NotFoundAgent()
    async with httpx.AsyncClient(transport=entra.mock_transport()) as jwks:
        app = create_app(
            BackendSettings(
                tenant_id=entra.tenant_id,
                backend_api_client_id=entra.backend_client_id,
                tools_api_scope=entra.tools_scope,
                agent_responses_url="http://127.0.0.1:8088/responses",
            ),
            validator=JwtValidator(
                tenant_id=entra.tenant_id,
                audience=entra.backend_client_id,
                http_client=jwks,
                required_scope=BACKEND_API_SCOPE_NAME,
            ),
            obo=FakeEntraOboExchanger(entra),
            foundry_token=None,
            agent_client=agent,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://backend"
        ) as client:
            response = await client.post(
                "/chat",
                json=body,
                headers={"Authorization": f"Bearer {entra.issue_user_token('finance')}"},
            )
    return response, agent


async def test_unknown_or_foreign_conversation_is_404() -> None:
    response, agent = await _chat({"message": "続き", "previous_response_id": "caresp_other_user"})
    assert response.status_code == 404
    assert response.json() == {
        "error": "conversation_not_found",
        "message": MSG_CONVERSATION_NOT_FOUND,
    }
    assert agent.bodies[0]["previous_response_id"] == "caresp_other_user"


async def test_404_without_continuation_is_still_an_agent_failure() -> None:
    response, _ = await _chat({"message": "こんにちは"})
    assert response.status_code == 502
    assert response.json()["error"] == "agent_failed"
