"""hosted agent デプロイの純関数部(zip ステージング+バージョン定義)。

HTTP/SDK を貼るのは hosting/deploy_hosted_agent.py のみ(db-routing-iq の
kb_setup.py と同じ「ペイロード組み立ては純関数・オフラインテストで固定」方針)。

実装前調査の要点(quickstart-hosted-agent / concepts/hosted-agents、2026-07):

- コードデプロイは **zip のルートに main.py と requirements.txt が必須**
  (quickstart の Troubleshooting に明記)。パッケージ本体
  (``hn_briefing_maf/``)も zip ルートへ同梱して import 可能にする
- ``create_version_from_code`` の定義は HostedAgentDefinition(cpu/memory +
  CodeConfiguration(runtime, entry_point, dependency_resolution=REMOTE_BUILD)
  + environment_variables + protocol_versions)。**コンテナプロトコルは
  responses 2.0.0**(1.0.0 は非推奨・猶予期間後ブロック)
- 環境変数がコンテナへの唯一の構成手段(バージョンごとに不変)。
  App Insights 接続文字列はプラットフォームが自動注入するため渡さない
- サンドボックスは 0.5vCPU/1GiB で十分(HN GET 1 本+モデル呼び出しのみ)
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

#: ポートのルート(src/hn_briefing_maf/ の 2 つ上)
PORT_ROOT = Path(__file__).resolve().parents[2]

#: zip ルートに置くファイル(hosted agent コードデプロイの必須規約)
REQUIRED_ZIP_ROOT_FILES = ("main.py", "requirements.txt")

#: コンテナプロトコル(2.0.0 必須 — 1.0.0 は非推奨)
RESPONSES_PROTOCOL_VERSION = "2.0.0"


def stage_hosted_agent_dir(dest: Path, *, port_root: Path = PORT_ROOT) -> Path:
    """デプロイ zip の中身を dest に組み立てる。

    - hosting/main.py / hosting/requirements.txt → zip ルート
    - src/hn_briefing_maf/ → zip ルート直下の hn_briefing_maf/
      (main.py の ``import hn_briefing_maf`` を成立させる)
    """
    dest.mkdir(parents=True, exist_ok=True)
    hosting_dir = port_root / "hosting"
    for name in REQUIRED_ZIP_ROOT_FILES:
        source = hosting_dir / name
        if not source.is_file():
            raise FileNotFoundError(f"hosting/{name} が見つからない: {source}")
        shutil.copy2(source, dest / name)
    shutil.copytree(
        port_root / "src" / "hn_briefing_maf",
        dest / "hn_briefing_maf",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        dirs_exist_ok=True,
    )
    return dest


def create_code_zip(staged_dir: Path, zip_path: Path) -> Path:
    """ステージ済みディレクトリを zip 化する(相対パス保存)。"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for path in sorted(staged_dir.rglob("*")):
            if path.is_file():
                zip_file.write(path, path.relative_to(staged_dir))
    return zip_path


def hosted_agent_definition_kwargs(
    *,
    project_endpoint: str,
    model: str,
    cpu: str = "0.5",
    memory: str = "1Gi",
    runtime: str = "python_3_13",
) -> dict[str, Any]:
    """HostedAgentDefinition に渡す値(SDK 型に依存しない素の dict)。

    deploy スクリプトが azure-ai-projects の型へ写像する。環境変数は
    hosting/main.py が読む 2 点のみ — API キーは渡さない(hosted 実行は
    agent identity + FoundryChatClient。README の学び参照)。
    """
    return {
        "cpu": cpu,
        "memory": memory,
        "runtime": runtime,
        "entry_point": ["python", "main.py"],
        "environment_variables": {
            "FOUNDRY_PROJECT_ENDPOINT": project_endpoint,
            "FOUNDRY_MODEL_NAME": model,
        },
        "protocols": [("responses", RESPONSES_PROTOCOL_VERSION)],
    }
