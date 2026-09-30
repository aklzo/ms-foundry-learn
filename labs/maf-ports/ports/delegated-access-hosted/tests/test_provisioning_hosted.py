"""hosted agent のデプロイ(provisioning/hosted_agent.py と scripts/deploy_hosted_agent.py)のオフラインテスト。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from delegated_access_maf.provisioning.hosted_agent import (
    DEFAULT_AGENT_NAMES,
    RESPONSES_PROTOCOL_VERSION,
    agent_responses_url,
    create_code_zip,
    hosted_agent_definition_kwargs,
    stage_hosted_agent_dir,
)

PORT_ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://aif-x.services.ai.azure.com/api/projects/maf-ports"
APIM = "https://apim-dah-abc.azure-api.net"
ACA = "https://ca-dah-tools-srv.example.japaneast.azurecontainerapps.io"


def test_zip_has_entrypoint_at_root_and_only_the_agent_side_of_the_package(tmp_path):
    staged = stage_hosted_agent_dir(tmp_path / "staged")
    zip_path = create_code_zip(staged, tmp_path / "agent.zip")
    names = set(zipfile.ZipFile(zip_path).namelist())
    assert {"main.py", "requirements.txt", "delegated_access_maf/__init__.py",
            "delegated_access_maf/contracts.py", "delegated_access_maf/redaction.py",
            "delegated_access_maf/agent/host.py"} <= names
    # 中間層(OBO の資格情報を扱う)・ツールサーバー・疑似 Entra・デプロイ用コードは入れない
    for excluded in ("backend/", "tools_server/", "devtools/", "provisioning/", "cli.py",
                     "jwt_validation.py"):
        assert not [n for n in names if n.startswith(f"delegated_access_maf/{excluded}")], excluded
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc")]
    assert not [n for n in names if n.startswith(".env")]


def test_staged_code_imports_on_its_own(tmp_path):
    """zip の中身だけで hosting/main.py が import できる(同梱漏れの検出)。"""
    pytest.importorskip("azure.ai.agentserver.responses")
    staged = stage_hosted_agent_dir(tmp_path / "staged")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    code = (
        "import main, delegated_access_maf, sys;"
        "print(delegated_access_maf.__file__)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=staged, env=env, capture_output=True, text=True, check=False,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    # リポジトリの src/ ではなく、ステージしたコピーが読まれている
    assert completed.stdout.strip().startswith(str(staged))


def test_definition_uses_protocol_2_and_carries_no_secrets():
    kwargs = hosted_agent_definition_kwargs(
        project_endpoint=ENDPOINT, model="gpt-5.4-mini", tools_base_url=APIM + "/", mode="apim"
    )
    assert kwargs["protocols"] == [("responses", RESPONSES_PROTOCOL_VERSION)]
    assert RESPONSES_PROTOCOL_VERSION == "2.0.0"
    assert kwargs["entry_point"] == ["python", "main.py"]
    assert kwargs["environment_variables"] == {
        "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT,
        "FOUNDRY_MODEL_NAME": "gpt-5.4-mini",
        "TOOLS_BASE_URL": APIM,  # 末尾の / は落とす(MCP URL = base + spec.path)
    }


@pytest.mark.parametrize(
    ("mode", "url"),
    [("apim", ACA), ("server", APIM), ("apim", "http://apim-dah-abc.azure-api.net"),
     ("server", "ftp://x")],
)
def test_tools_base_url_must_match_the_mode(mode, url):
    with pytest.raises(ValueError):
        hosted_agent_definition_kwargs(
            project_endpoint=ENDPOINT, model="m", tools_base_url=url, mode=mode
        )


def test_agent_names_and_responses_url():
    assert DEFAULT_AGENT_NAMES == {"apim": "delegated-access-apim",
                                   "server": "delegated-access-server"}
    assert agent_responses_url(ENDPOINT + "/", "delegated-access-apim") == (
        f"{ENDPOINT}/agents/delegated-access-apim/endpoint/protocols/openai/responses"
        "?api-version=v1"
    )


def test_sdk_types_build_offline():
    pytest.importorskip("azure.ai.projects")
    from delegated_access_maf.provisioning.hosted_agent import build_definition, route_all_traffic

    kwargs = hosted_agent_definition_kwargs(
        project_endpoint=ENDPOINT, model="m", tools_base_url=ACA, mode="server"
    )
    definition = build_definition(kwargs)
    assert definition["environment_variables"]["TOOLS_BASE_URL"] == ACA
    assert definition["protocol_versions"][0]["version"] == "2.0.0"
    routing = route_all_traffic("3")
    rule = routing["version_selector"]["version_selection_rules"][0]
    assert rule["agent_version"] == "3" and rule["traffic_percentage"] == 100


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "deploy_hosted_agent_script", PORT_ROOT / "scripts" / "deploy_hosted_agent.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_defaults_to_dry_run_and_prints_agent_url(monkeypatch, capsys):
    module = _load_script()
    monkeypatch.setattr(module, "_load_env", lambda: None)  # .env を読まない

    def no_deploy(*_a, **_k):
        raise AssertionError("dry-run must not deploy")

    monkeypatch.setattr(module, "_deploy", no_deploy)
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("FOUNDRY_MODEL_NAME", "gpt-5.4-mini")
    monkeypatch.delenv("TOOLS_BASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["deploy", "--mode", "apim", "--tools-base-url", APIM])
    module.main()
    out = capsys.readouterr().out
    definition = json.loads(out[: out.index("AGENT_RESPONSES_URL=")])
    assert definition["agent_name"] == "delegated-access-apim"
    assert definition["environment_variables"]["TOOLS_BASE_URL"] == APIM
    assert f"AGENT_RESPONSES_URL={ENDPOINT}/agents/delegated-access-apim/" in out


def test_script_rejects_mode_url_mismatch(monkeypatch, capsys):
    module = _load_script()
    monkeypatch.setattr(module, "_load_env", lambda: None)
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("FOUNDRY_MODEL_NAME", "m")
    monkeypatch.setattr(sys, "argv", ["deploy", "--mode", "server", "--tools-base-url", APIM])
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 2
    assert "方式 B" in capsys.readouterr().err
