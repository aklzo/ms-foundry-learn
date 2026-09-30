"""hosted agent デプロイの純関数部(zip ステージング+バージョン定義)。SDK を呼ぶのは
``scripts/deploy_hosted_agent.py`` だけ(Port 11 の hosting_setup.py と同じ分担)。

- コードデプロイは **zip のルートに main.py と requirements.txt が必須**。パッケージ
  ``delegated_access_maf/`` も zip ルート直下に同梱する
- 同梱するのはエージェントが実行時に使う部分だけ(``agent/`` ``contracts.py``
  ``redaction.py``)。中間層(OBO の資格情報を扱う ``backend/``)・ツールサーバー・
  オフライン用の疑似 Entra・このデプロイ用コードはコンテナに入れない
  — 委任トークンを受け取るコンテナに余計なコードを置かない
- コンテナプロトコルは **responses 2.0.0**(``x-client-*`` 転送と ``x-ms-user-identity`` による
  利用者単位の分離は 2.0.0 前提)
- 環境変数がコンテナへの唯一の構成手段(バージョンごとに不変)。``TOOLS_BASE_URL`` が
  方式 A(APIM)/ 方式 B(ツールサーバー直)を決めるので、方式ごとに別エージェント名で並べる
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

PORT_ROOT = Path(__file__).resolve().parents[3]
PACKAGE = "delegated_access_maf"

#: zip ルートに置くファイル(hosted agent コードデプロイの必須規約)
REQUIRED_ZIP_ROOT_FILES = ("main.py", "requirements.txt")

#: コンテナに入れるパッケージの中身(エージェントの実行に要るものだけ)
PACKAGE_INCLUDE = ("__init__.py", "contracts.py", "redaction.py", "agent")

RESPONSES_PROTOCOL_VERSION = "2.0.0"

Mode = Literal["apim", "server"]

#: 方式ごとの既定のエージェント名(2 つ並べて中間層の AGENT_RESPONSES_URL で切り替える)
DEFAULT_AGENT_NAMES: dict[str, str] = {
    "apim": "delegated-access-apim",
    "server": "delegated-access-server",
}


def stage_hosted_agent_dir(dest: Path, *, port_root: Path = PORT_ROOT) -> Path:
    """デプロイ zip の中身を dest に組み立てる。"""
    dest.mkdir(parents=True, exist_ok=True)
    hosting_dir = port_root / "hosting"
    for name in REQUIRED_ZIP_ROOT_FILES:
        source = hosting_dir / name
        if not source.is_file():
            raise FileNotFoundError(f"hosting/{name} が見つからない: {source}")
        shutil.copy2(source, dest / name)
    package_src = port_root / "src" / PACKAGE
    package_dest = dest / PACKAGE
    package_dest.mkdir(exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for entry in PACKAGE_INCLUDE:
        source = package_src / entry
        if source.is_dir():
            shutil.copytree(source, package_dest / entry, ignore=ignore, dirs_exist_ok=True)
        elif source.is_file():
            shutil.copy2(source, package_dest / entry)
        else:
            raise FileNotFoundError(f"パッケージに {entry} が見つからない: {source}")
    return dest


def create_code_zip(staged_dir: Path, zip_path: Path) -> Path:
    """ステージ済みディレクトリを zip 化する(相対パス保存)。"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for path in sorted(staged_dir.rglob("*")):
            if path.is_file():
                zip_file.write(path, path.relative_to(staged_dir))
    return zip_path


def validate_tools_base_url(url: str, mode: Mode) -> str:
    """デプロイ前の取り違え防止(方式 A に APIM 以外、方式 B に APIM を渡していないか)。"""
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError(f"TOOLS_BASE_URL は https の絶対 URL にしてください(指定値: {url!r})")
    is_apim = parts.hostname.endswith(".azure-api.net")
    if mode == "apim" and not is_apim:
        raise ValueError(f"方式 A(apim)の TOOLS_BASE_URL は APIM ゲートウェイ(*.azure-api.net): {url}")
    if mode == "server" and is_apim:
        raise ValueError(f"方式 B(server)の TOOLS_BASE_URL はツールサーバー直(Container Apps): {url}")
    return url.strip().rstrip("/")


def hosted_agent_definition_kwargs(
    *,
    project_endpoint: str,
    model: str,
    tools_base_url: str,
    mode: Mode,
    cpu: str = "0.5",
    memory: str = "1Gi",
    runtime: str = "python_3_13",
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """HostedAgentDefinition に渡す値(SDK 型に依存しない素の dict)。

    環境変数に秘密は入れない: モデルは agent identity、ツールは要求ごとに中間層から届く
    委任トークン(``x-client-tools-access-token``)。
    """
    env = {
        "FOUNDRY_PROJECT_ENDPOINT": project_endpoint,
        "FOUNDRY_MODEL_NAME": model,
        "TOOLS_BASE_URL": validate_tools_base_url(tools_base_url, mode),
        **(extra_env or {}),
    }
    return {
        "cpu": cpu,
        "memory": memory,
        "runtime": runtime,
        "entry_point": ["python", "main.py"],
        "environment_variables": env,
        "protocols": [("responses", RESPONSES_PROTOCOL_VERSION)],
    }


def build_definition(kwargs: dict[str, Any]) -> Any:
    """``hosted_agent_definition_kwargs`` の値を azure-ai-projects の型へ写す(hosting extra が必要)。"""
    from azure.ai.projects.models import (
        CodeConfiguration,
        CodeDependencyResolution,
        HostedAgentDefinition,
        ProtocolVersionRecord,
    )

    return HostedAgentDefinition(
        cpu=kwargs["cpu"],
        memory=kwargs["memory"],
        code_configuration=CodeConfiguration(
            runtime=kwargs["runtime"],
            entry_point=kwargs["entry_point"],
            dependency_resolution=CodeDependencyResolution.REMOTE_BUILD,
        ),
        environment_variables=kwargs["environment_variables"],
        protocol_versions=[
            ProtocolVersionRecord(protocol=protocol, version=version)
            for protocol, version in kwargs["protocols"]
        ],
    )


def route_all_traffic(version: str) -> Any:
    """エンドポイントを 1 バージョンに 100% 向ける設定(hosted agent はトラフィック分割不可)。"""
    from azure.ai.projects.models import (
        AgentEndpointConfig,
        FixedRatioVersionSelectionRule,
        ProtocolConfiguration,
        ResponsesProtocolConfiguration,
        VersionSelector,
    )

    return AgentEndpointConfig(
        version_selector=VersionSelector(
            version_selection_rules=[
                FixedRatioVersionSelectionRule(agent_version=version, traffic_percentage=100)
            ]
        ),
        protocol_configuration=ProtocolConfiguration(responses=ResponsesProtocolConfiguration()),
    )


def agent_responses_url(project_endpoint: str, agent_name: str) -> str:
    """中間層の ``AGENT_RESPONSES_URL``(use-on-behalf-of-flow の書式)。"""
    base = project_endpoint.rstrip("/")
    return f"{base}/agents/{agent_name}/endpoint/protocols/openai/responses?api-version=v1"
