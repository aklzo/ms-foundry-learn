"""ツールサーバーの設定・起動口・コンテナ定義・インデックス作成スクリプト(ドライラン)。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest

from delegated_access_maf.tools_server import main as tools_main
from delegated_access_maf.tools_server.docs_search import AzureSearchDocs, InMemoryDocs
from delegated_access_maf.tools_server.settings import (
    DEFAULT_SUPPLIERS_DATA,
    PORT_ROOT,
    SettingsError,
    ToolsServerSettings,
)

BASE_ENV = {"ENTRA_TENANT_ID": "tenant", "TOOLS_API_CLIENT_ID": "tools-client"}


def test_settings_defaults_and_required_values():
    s = ToolsServerSettings.from_env(BASE_ENV)
    assert (s.enforcement_mode, s.search_endpoint, s.search_index, s.port) == (
        "server",
        None,
        "internal-docs",
        8080,
    )
    assert s.suppliers_data == DEFAULT_SUPPLIERS_DATA
    with pytest.raises(SettingsError, match="TOOLS_API_CLIENT_ID"):
        ToolsServerSettings.from_env({"ENTRA_TENANT_ID": "t"})
    with pytest.raises(SettingsError, match="ENFORCEMENT_MODE"):
        ToolsServerSettings.from_env({**BASE_ENV, "ENFORCEMENT_MODE": "gateway"})
    with pytest.raises(SettingsError, match="APIM_GATEWAY_SECRET"):
        ToolsServerSettings.from_env(
            {**BASE_ENV, "ENFORCEMENT_MODE": "apim"}
        )  # 迂回を許して起動しない
    apim = ToolsServerSettings.from_env(
        {
            **BASE_ENV,
            "ENFORCEMENT_MODE": "APIM",
            "PORT": "9000",
            "APIM_GATEWAY_SECRET": "s3cr3t-value",
        }
    )
    assert (apim.enforcement_mode, apim.port, apim.apim_gateway_secret) == (
        "apim",
        9000,
        "s3cr3t-value",
    )
    # 秘密は repr(起動ログ・例外)に出さない
    keyed = ToolsServerSettings.from_env({**BASE_ENV, "SEARCH_API_KEY": "search-key-value"})
    assert "s3cr3t-value" not in repr(apim) and "search-key-value" not in repr(keyed)


def test_docs_backend_follows_search_endpoint(monkeypatch):
    local = tools_main.build_docs_search(ToolsServerSettings.from_env(BASE_ENV))
    assert isinstance(local, InMemoryDocs)

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return AzureSearchDocs(object())

    monkeypatch.setattr(AzureSearchDocs, "create", staticmethod(fake_create))
    remote = tools_main.build_docs_search(
        ToolsServerSettings.from_env(
            {**BASE_ENV, "SEARCH_ENDPOINT": "https://s.search.windows.net", "SEARCH_INDEX": "ix"}
        )
    )
    assert isinstance(remote, AzureSearchDocs)
    assert captured == {"endpoint": "https://s.search.windows.net", "index": "ix", "api_key": None}


@pytest.mark.parametrize("mode", ["server", "apim"])
async def test_build_app_serves_health(mode):
    env = {**BASE_ENV, "ENFORCEMENT_MODE": mode, "APIM_GATEWAY_SECRET": "s3cr3t-value"}
    app = tools_main.build_app(ToolsServerSettings.from_env(env))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as http,
    ):
        r = await http.get("/healthz")
        unauthenticated = await http.post("/docs/mcp", json={})
    assert r.status_code == 200 and r.json()["enforcement_mode"] == mode
    # apim 方式はゲートウェイの秘密がない時点で 403(トークンを見る前に止める)
    assert unauthenticated.status_code == (401 if mode == "server" else 403)
    # 検証器: server 方式はスコープまで、apim 方式は署名・宛先・期限だけ
    validator = app.state.validator
    assert validator.required_scope == ("Tools.Access" if mode == "server" else None)
    assert validator.audience == "tools-client"


def test_dockerfile_runs_the_tools_server_with_bundled_data():
    dockerfile = (PORT_ROOT / "docker" / "tools" / "Dockerfile").read_text(encoding="utf-8")
    assert "delegated_access_maf.tools_server.main" in dockerfile
    assert "COPY data" in dockerfile and "COPY src" in dockerfile
    assert "/healthz" in dockerfile
    ignore = (PORT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    for secret in (".env", ".cache"):
        assert secret in ignore.split()  # MSAL のトークンキャッシュや .env をビルドに送らない


def _load_setup_index():
    path = PORT_ROOT / "scripts" / "setup_index.py"
    spec = importlib.util.spec_from_file_location("setup_index", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_setup_index_dry_run_prints_requests_without_network(monkeypatch, capsys):
    module = _load_setup_index()
    monkeypatch.delenv("SEARCH_ENDPOINT", raising=False)
    assert module.main([]) == 0
    out = capsys.readouterr().out
    assert "PUT https://<search-service>.search.windows.net/indexes/internal-docs" in out
    assert '"@search.action": "mergeOrUpload"' in out


def test_setup_index_schema_follows_security_filter_pattern():
    module = _load_setup_index()
    fields = {f["name"]: f for f in module.build_index_definition("ix")["fields"]}
    roles = fields["allowed_roles"]
    assert roles["type"] == "Collection(Edm.String)"
    assert roles["filterable"] is True and roles["retrievable"] is False
    assert fields["content"]["analyzer"] == "ja.microsoft"
    docs = module.build_documents()
    assert {tuple(d["allowed_roles"]) for d in docs} == {("Employee",), ("Docs.Finance",)}
    assert Path(PORT_ROOT / "data" / "docs").is_dir()
