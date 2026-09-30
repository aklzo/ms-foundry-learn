"""infra/(Bicep・APIM ポリシー・カスタムロール)と .env.example が contracts.py と食い違わないことを固定する。

Bicep 自体の文法は ``az bicep build`` で確かめる(runbook §4。ネットワーク不要だが az が要るので
pytest には入れない)。ここではテキストとして読み、部品間の名前の一致だけを見る。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from delegated_access_maf.contracts import MCP_SERVERS
from delegated_access_maf.provisioning.entra import (
    FOUNDRY_AGENT_CONSUMER_ROLE_ID,
    USER_IDENTITY_IMPERSONATION_ACTION,
)
from delegated_access_maf.tools_server.settings import DEFAULT_PORT, DEFAULT_SEARCH_INDEX

PORT_ROOT = Path(__file__).resolve().parents[1]
INFRA = PORT_ROOT / "infra"
MAIN = (INFRA / "main.bicep").read_text(encoding="utf-8")
APIM = (INFRA / "modules" / "apim.bicep").read_text(encoding="utf-8")
APIM_API = (INFRA / "modules" / "apim-mcp-api.bicep").read_text(encoding="utf-8")
TOOLS_APP = (INFRA / "modules" / "tools-app.bicep").read_text(encoding="utf-8")

#: APIM Consumption のポリシー文書の上限(gateway overview の Gateway runtime limits)
CONSUMPTION_POLICY_LIMIT_BYTES = 16 * 1024


def _named_values_created() -> set[str]:
    return set(re.findall(r"namedValues@[^']+' = \{\s*parent: apim\s*name: '([^']+)'", APIM))


def test_apim_apis_match_the_contract_paths():
    apis = dict(re.findall(r"\{ name: '([^']+)', path: '([^']+)' \}", MAIN))
    assert set(apis) == {spec.name for spec in MCP_SERVERS}
    # API パス + 操作 POST /mcp = 契約パス(TOOLS_BASE_URL + spec.path が APIM でも同じ URL になる)
    assert "method: 'POST'" in APIM_API and "urlTemplate: '/mcp'" in APIM_API
    for spec in MCP_SERVERS:
        assert f"/{apis[spec.name]}/mcp" == spec.path


@pytest.mark.parametrize("spec", MCP_SERVERS, ids=lambda s: s.name)
def test_each_server_has_a_policy_file_loaded_by_bicep(spec):
    policy = INFRA / "apim" / "policies" / f"{spec.name}.xml"
    assert policy.is_file()
    assert f"'{spec.name}': loadTextContent('../apim/policies/{spec.name}.xml')" in APIM or (
        f"{spec.name}: loadTextContent('../apim/policies/{spec.name}.xml')" in APIM
    )
    assert policy.stat().st_size < CONSUMPTION_POLICY_LIMIT_BYTES
    # ポリシーが参照する Named Value はすべて Bicep が作る(無いとポリシーの保存が失敗する)
    referenced = set(re.findall(r"\{\{([A-Za-z0-9._-]+)\}\}", policy.read_text(encoding="utf-8")))
    assert referenced <= _named_values_created(), referenced - _named_values_created()


def test_named_values_are_the_ones_the_policies_expect():
    created = _named_values_created()
    assert {"dah-tenant-id", "dah-tools-api-client-id", "dah-gateway-secret"} <= created
    # ゲートウェイ共有シークレットは secret 扱い
    block = APIM[APIM.index("name: 'dah-gateway-secret'"):]
    assert re.search(r"secret: true", block[: block.index("}")])


def test_tools_app_matches_the_server_settings():
    assert f"param toolsPort int = {DEFAULT_PORT}" in TOOLS_APP
    for name in ("ENFORCEMENT_MODE", "ENTRA_TENANT_ID", "TOOLS_API_CLIENT_ID", "SEARCH_ENDPOINT",
                 "SEARCH_INDEX", "AZURE_CLIENT_ID", "PORT"):
        assert f"name: '{name}'" in TOOLS_APP, name
    # 共有シークレットは secretRef で渡す(平文の value にしない)
    assert "name: 'APIM_GATEWAY_SECRET', secretRef: 'apim-gateway-secret'" in TOOLS_APP
    assert "maxReplicas: 1" in TOOLS_APP  # 取引先マスタはプロセス内メモリ
    assert f"param searchIndex string = '{DEFAULT_SEARCH_INDEX}'" in MAIN
    # 2 モードのアプリがあり、apim モードにだけ共有シークレットを渡す
    assert "enforcementMode: 'server'" in MAIN and "enforcementMode: 'apim'" in MAIN
    assert MAIN.count("gatewaySecret: apimGatewaySecret") == 2  # apim モードのアプリと APIM


def test_apim_is_consumption_without_subscription_keys_and_without_payload_logging():
    assert "name: 'Consumption'" in APIM
    assert "subscriptionRequired: false" in APIM_API
    assert "format: 'rawxml'" in APIM_API
    assert "bytes: 0" in APIM and "headers: []" in APIM


def test_custom_role_file_and_role_ids():
    role = json.loads((INFRA / "roles" / "foundry-user-identity-impersonation.json").read_text())
    assert role["IsCustom"] is True
    assert role["DataActions"] == [USER_IDENTITY_IMPERSONATION_ACTION]
    assert FOUNDRY_AGENT_CONSUMER_ROLE_ID == "eed3b665-ab3a-47b6-8f48-c9382fb1dad6"


def test_env_example_lists_every_variable():
    text = (PORT_ROOT / ".env.example").read_text(encoding="utf-8")
    names = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", text, flags=re.MULTILINE))
    expected = {
        # 共通
        "ENTRA_TENANT_ID", "TOOLS_API_CLIENT_ID", "TOOLS_API_SCOPE",
        # ツールサーバー
        "ENFORCEMENT_MODE", "SEARCH_ENDPOINT", "SEARCH_INDEX", "SEARCH_API_KEY", "SUPPLIERS_DATA",
        "APIM_GATEWAY_SECRET", "PORT",
        # バックエンド
        "BACKEND_API_CLIENT_ID", "BACKEND_CLIENT_SECRET", "AGENT_RESPONSES_URL", "FOUNDRY_SCOPE",
        "BACKEND_PORT",
        # エージェント
        "TOOLS_BASE_URL", "FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL_NAME", "MCP_TIMEOUT_SECONDS",
        # CLI
        "BACKEND_URL", "DELEGATED_ACCESS_CACHE_DIR",
    }
    assert expected <= names, expected - names
    # 秘密の実値を雛形に書かない
    assert re.search(r"^BACKEND_CLIENT_SECRET=$", text, flags=re.MULTILINE)
    assert re.search(r"^APIM_GATEWAY_SECRET=$", text, flags=re.MULTILINE)
