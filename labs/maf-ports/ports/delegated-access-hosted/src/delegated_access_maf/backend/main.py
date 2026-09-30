"""中間層バックエンドの起動(ライブ用)。

    uv run python -m delegated_access_maf.backend.main       # 既定 :8000(BACKEND_PORT)

必要な環境変数は settings.py と .env.example を参照。MSAL の機密クライアント 1 つで
OBO(ツール API 宛て)と Foundry 用トークン(``FOUNDRY_SCOPE``)の両方を取る。
エージェントの URL がループバック(ローカルコンテナ)なら Foundry 用トークンは取らない。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from ..contracts import BACKEND_API_SCOPE_NAME
from ..jwt_validation import JwtValidator
from ..redaction import install_log_redaction
from .agent_client import HttpAgentClient
from .app import create_app
from .obo import MsalFoundryTokenProvider, MsalOboExchanger, build_msal_app
from .settings import BackendSettings

#: ポートのルート(src/delegated_access_maf/backend/main.py から 3 つ上)
PORT_ROOT = Path(__file__).resolve().parents[3]

#: hosted agent の応答はモデル+ツール呼び出しを含むので長めに待つ
AGENT_TIMEOUT_SECONDS = 180.0


def build_app(settings: BackendSettings | None = None) -> FastAPI:
    settings = settings or BackendSettings.from_env()
    jwks_http = httpx.AsyncClient(timeout=10.0)
    agent_http = httpx.AsyncClient(timeout=AGENT_TIMEOUT_SECONDS, follow_redirects=False)
    msal_app = build_msal_app(settings)
    app = create_app(
        settings,
        validator=JwtValidator(
            tenant_id=settings.tenant_id,
            audience=settings.backend_api_client_id,
            http_client=jwks_http,
            required_scope=BACKEND_API_SCOPE_NAME,
        ),
        obo=MsalOboExchanger(msal_app, settings.tools_api_scope),
        foundry_token=None
        if settings.local_agent
        else MsalFoundryTokenProvider(msal_app, settings.foundry_scope),
        agent_client=HttpAgentClient(agent_http, settings.agent_responses_url),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            await jwks_http.aclose()
            await agent_http.aclose()

    app.router.lifespan_context = lifespan
    return app


def main() -> None:  # pragma: no cover - ライブ実行のみ
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv(PORT_ROOT / ".env")
    settings = BackendSettings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    install_log_redaction()
    mode = "local container" if settings.local_agent else "Foundry hosted agent"
    logging.getLogger(__name__).info("agent: %s (%s)", settings.agent_responses_url, mode)
    uvicorn.run(build_app(settings), host="127.0.0.1", port=settings.port, log_config=None)


if __name__ == "__main__":  # pragma: no cover
    main()
