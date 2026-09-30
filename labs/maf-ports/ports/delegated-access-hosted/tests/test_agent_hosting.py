"""hosted agent のエントリポイントと部品単体(実デプロイなし)。

- hosting/main.py の実 import と、依存(requirements.txt)と pyproject の hosting extra の一致
- 設定(トークンを送ってよい宛先の検証)
- 401/403 → JSON-RPC エラーの読み替え(transport)と、トークンのマスク(redaction)
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import tomllib
from pathlib import Path

import httpx
import pytest

from delegated_access_maf.agent.settings import AgentSettings, SettingsError
from delegated_access_maf.agent.transport import (
    JSONRPC_FORBIDDEN,
    JSONRPC_UNAUTHORIZED,
    AuthzMappingTransport,
    find_authz_failure,
)
from delegated_access_maf.contracts import DOCS, TOOLS_TOKEN_HEADER
from delegated_access_maf.redaction import (
    REDACTED,
    RedactingLogFilter,
    Redactor,
    install_log_redaction,
    redact_headers,
    secrets_scope,
)

PORT_ROOT = Path(__file__).resolve().parents[1]
HOSTING_MAIN = PORT_ROOT / "hosting" / "main.py"
JWT_LIKE = "eyJhbGciOiJSUzI1NiJ9.eyJvaWQiOiJ4eHh4In0.c2lnbmF0dXJlLXZhbHVl"

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# --- エントリポイント ---------------------------------------------------------------------


def test_hosting_main_uses_the_agent_server_sdk_directly() -> None:
    source = HOSTING_MAIN.read_text(encoding="utf-8")
    assert "build_host" in source and "DelegatedAccessRuntime" in source
    assert "from agent_framework_foundry_hosting" not in source  # ResponsesHostServer は使わない
    assert "DefaultAzureCredential" in source and "FoundryChatClient" in source
    assert "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT" in source
    assert "install_log_redaction" in source

    pytest.importorskip("azure.ai.agentserver.responses")  # hosting extra
    spec = importlib.util.spec_from_file_location("hosting_main", HOSTING_MAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # main() は呼ばない(env 不要)
    assert callable(module.main)


def _names(requirements: list[str]) -> set[str]:
    return {
        re.split(r"[<>=!\[ ;]", r.strip(), maxsplit=1)[0].lower() for r in requirements if r.strip()
    }


def test_requirements_match_the_hosting_extra() -> None:
    lines = [
        line
        for line in (PORT_ROOT / "hosting" / "requirements.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    required = _names(lines)
    pyproject = tomllib.loads((PORT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    hosting = _names(pyproject["project"]["optional-dependencies"]["hosting"])
    # コンテナに要る hosting extra の中身(デプロイ用の azure-ai-projects は除く)
    assert hosting - {"azure-ai-projects"} <= required
    assert {"agent-framework-core", "mcp", "httpx"} <= required
    assert "agent-framework-foundry-hosting" not in required


def test_agent_package_only_imports_what_the_container_ships() -> None:
    """デプロイ zip にはパッケージの agent/・contracts.py・redaction.py だけが入る
    (provisioning/hosted_agent.py の PACKAGE_INCLUDE)。それ以外に依存したら起動できない。"""
    package = PORT_ROOT / "src" / "delegated_access_maf"
    shipped = {"contracts", "redaction", "agent"}
    sources = [*sorted((package / "agent").glob("*.py")), package / "redaction.py", HOSTING_MAIN]
    for path in sources:
        text = path.read_text(encoding="utf-8")
        relative = set(re.findall(r"^\s*from \.\.(\w+)", text, re.MULTILINE))
        absolute = set(re.findall(r"^\s*from delegated_access_maf\.(\w+)", text, re.MULTILINE))
        assert relative | absolute <= shipped, (path.name, relative | absolute)


# --- 設定 ------------------------------------------------------------------------------------


def test_agent_settings_from_env() -> None:
    settings = AgentSettings.from_env(
        {
            "TOOLS_BASE_URL": "https://apim.azure-api.net/",
            "FOUNDRY_PROJECT_ENDPOINT": "https://acct.services.ai.azure.com/api/projects/p",
            "FOUNDRY_MODEL_NAME": "gpt-fallback",
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": "gpt-injected",
        }
    )
    assert settings.mcp_url(DOCS) == "https://apim.azure-api.net/docs/mcp"
    assert settings.model == "gpt-injected"  # プラットフォーム注入を優先
    assert (
        AgentSettings(tools_base_url="http://localhost:8080").mcp_url(DOCS)
        == "http://localhost:8080/docs/mcp"
    )


@pytest.mark.parametrize(
    "url",
    ["http://tools.contoso.com", "ftp://tools", "https://tools?x=1", "tools.contoso.com", ""],
)
def test_tokens_are_only_sent_to_https_or_loopback(url) -> None:
    with pytest.raises(SettingsError):
        AgentSettings.from_env({"TOOLS_BASE_URL": url})


# --- 401/403 の読み替え ---------------------------------------------------------------------


async def _through_mapping(status: int, payload: dict) -> httpx.Response:
    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": "denied", "echo": request.headers.get("authorization")},
            headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
        )

    async with httpx.AsyncClient(
        transport=AuthzMappingTransport(httpx.MockTransport(upstream))
    ) as client:
        return await client.post(
            "https://tools/docs/mcp", json=payload, headers={"Authorization": "Bearer secret"}
        )


@pytest.mark.parametrize(
    ("status", "code"), [(401, JSONRPC_UNAUTHORIZED), (403, JSONRPC_FORBIDDEN)]
)
async def test_authz_status_becomes_a_jsonrpc_error_with_the_same_id(status, code) -> None:
    response = await _through_mapping(status, {"jsonrpc": "2.0", "id": 7, "method": "tools/call"})
    body = response.json()
    assert response.status_code == 200
    assert body["id"] == 7 and body["error"]["code"] == code
    assert body["error"]["data"] == {
        "http_status": status,
        "www_authenticate": 'Bearer error="insufficient_scope"',
    }
    assert "secret" not in response.text  # サーバーの応答本文(反射を含みうる)は捨てる


async def test_notifications_and_other_statuses_pass_through() -> None:
    notification = await _through_mapping(
        403, {"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    assert notification.status_code == 202
    ok = await _through_mapping(500, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert ok.status_code == 500


def test_find_authz_failure_walks_the_exception_chain() -> None:
    from mcp.shared.exceptions import McpError
    from mcp.types import ErrorData

    inner = McpError(
        ErrorData(code=JSONRPC_FORBIDDEN, message="forbidden", data={"http_status": 403})
    )
    try:
        try:
            raise inner
        except McpError as ex:
            raise RuntimeError("wrapped") from ex
    except RuntimeError as outer:
        failure = find_authz_failure(outer)
    assert failure is not None and failure.kind == "forbidden" and failure.http_status == 403
    assert find_authz_failure(RuntimeError("other")) is None


# --- マスク ----------------------------------------------------------------------------------


def test_redactor_masks_known_secrets_jwts_and_bearer_values() -> None:
    redactor = Redactor(["opaque-secret-value", None, "short"])
    text = f"a opaque-secret-value b {JWT_LIKE} c Bearer abcdefgh12345 d short"
    masked = redactor.redact(text)
    assert "opaque-secret-value" not in masked
    assert JWT_LIKE not in masked
    assert "abcdefgh12345" not in masked
    assert masked.endswith("short")  # 8 文字未満は完全一致マスクの対象外
    assert redactor.redact_value({"q": [JWT_LIKE, 1]}) == {"q": [REDACTED, 1]}
    assert redact_headers(
        {"Authorization": "Bearer x", TOOLS_TOKEN_HEADER: "y", "Accept": "a"}
    ) == {
        "Authorization": REDACTED,
        TOOLS_TOKEN_HEADER: REDACTED,
        "Accept": "a",
    }


def test_log_filter_masks_messages_args_and_tracebacks() -> None:
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("test.redaction")
    handler = Capture()
    logger.addHandler(handler)
    logger.propagate = False
    try:
        assert install_log_redaction(logger) == 1
        assert install_log_redaction(logger) == 0  # 重複しない
        with secrets_scope("plain-opaque-token"):
            logger.warning("token=%s jwt=%s", "plain-opaque-token", JWT_LIKE)
            try:
                raise ValueError(f"bad header Bearer {JWT_LIKE}")
            except ValueError:
                logger.exception("failed")
        logger.warning("outside scope plain-opaque-token")
    finally:
        logger.removeHandler(handler)

    assert records[0].getMessage() == f"token={REDACTED} jwt={REDACTED}"
    assert records[1].exc_info is None and JWT_LIKE not in records[1].exc_text
    assert "ValueError" in records[1].exc_text
    assert "plain-opaque-token" in records[2].getMessage()  # スコープ外の不透明値は形では分からない
    assert isinstance(handler.filters[0], RedactingLogFilter)


def test_metadata_values_fit_the_sdk_limit() -> None:
    from delegated_access_maf.agent import signals
    from delegated_access_maf.agent.runtime import reauth_outcome

    meta = reauth_outcome("x", "Bearer " + "a" * 1000).metadata()
    assert len(meta[signals.META_WWW_AUTHENTICATE]) <= signals.MAX_METADATA_VALUE_LENGTH
    assert json.dumps(meta)
