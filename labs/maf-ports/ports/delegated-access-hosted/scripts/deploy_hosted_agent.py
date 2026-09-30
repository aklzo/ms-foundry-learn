"""hosted agent のデプロイ(SDK 経路)。**既定は dry-run**(zip の中身と定義を表示するだけ)。

    uv sync --extra dev --extra hosting
    # 方式 A: ツールは APIM 経由(Bicep の出力 apimGatewayUrl)
    uv run python scripts/deploy_hosted_agent.py --mode apim --tools-base-url https://apim-dah-xxx.azure-api.net
    # 方式 B: ツールサーバー直(Bicep の出力 toolsServerUrl)
    uv run python scripts/deploy_hosted_agent.py --mode server --tools-base-url https://ca-dah-tools-srv.<env>.azurecontainerapps.io
    # 確認したら --apply を付けて実行(az login 済み・Foundry Project Manager 以上)
    uv run python scripts/deploy_hosted_agent.py --mode apim --tools-base-url ... --apply

経路は Port 11 と同じ ``AIProjectClient.agents.create_version_from_code``(zip = hosting/main.py +
hosting/requirements.txt + ``delegated_access_maf/`` のエージェント部分、REMOTE_BUILD)→
provisioning をポーリング → ``update_details`` で新バージョンに 100% ルーティング。

方式ごとに別名のエージェントを作る(既定 ``delegated-access-apim`` / ``delegated-access-server``)。
コンテナの環境変数はバージョンごとに不変なので、TOOLS_BASE_URL を切り替えるより 2 つ並べて
中間層の ``AGENT_RESPONSES_URL`` を差し替える方が比較しやすい。最後に中間層用の
``AGENT_RESPONSES_URL`` を表示する。

設定: ``FOUNDRY_PROJECT_ENDPOINT`` / ``FOUNDRY_MODEL_NAME``(なければ lab 共通の ``FOUNDRY_MODEL``)
/ ``TOOLS_BASE_URL``(``--tools-base-url`` が優先)。ポートの ``.env`` → lab ルートの ``.env`` の順に読む。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

PORT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT_ROOT / "src"))

from delegated_access_maf.provisioning.hosted_agent import (
    DEFAULT_AGENT_NAMES,
    agent_responses_url,
    build_definition,
    create_code_zip,
    hosted_agent_definition_kwargs,
    route_all_traffic,
    stage_hosted_agent_dir,
)

POLL_INTERVAL_SECONDS = 10.0


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    load_dotenv(PORT_ROOT / ".env")
    load_dotenv(PORT_ROOT.parents[1] / ".env")  # labs/maf-ports/.env(既存の値は上書きしない)


def main() -> None:
    parser = argparse.ArgumentParser(description="delegated-access hosted agent のデプロイ")
    parser.add_argument("--mode", choices=["apim", "server"], required=True,
                        help="apim = 方式 A(APIM で判定)/ server = 方式 B(MCP サーバーで判定)")
    parser.add_argument("--tools-base-url", default=None,
                        help="MCP の入口(既定は環境変数 TOOLS_BASE_URL)")
    parser.add_argument("--agent-name", default=None, help="既定 delegated-access-<mode>")
    parser.add_argument("--cpu", default="0.5", help="サンドボックス vCPU(0.5/1/2)")
    parser.add_argument("--memory", default="1Gi", help="サンドボックスメモリ(1Gi/2Gi/4Gi)")
    parser.add_argument("--env", action="append", default=[], metavar="KEY=VALUE",
                        help="コンテナに追加で渡す環境変数(例 MCP_TIMEOUT_SECONDS=25)。秘密は渡さない")
    parser.add_argument("--timeout", type=float, default=900.0, help="provisioning 待ち上限秒")
    parser.add_argument("--apply", action="store_true", help="実際にデプロイする(既定は dry-run)")
    args = parser.parse_args()

    _load_env()
    project_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    model = (os.environ.get("FOUNDRY_MODEL_NAME") or os.environ.get("FOUNDRY_MODEL") or "").strip()
    tools_base_url = (args.tools_base_url or os.environ.get("TOOLS_BASE_URL") or "").strip()
    missing = [n for n, v in (("FOUNDRY_PROJECT_ENDPOINT", project_endpoint),
                              ("FOUNDRY_MODEL_NAME", model),
                              ("TOOLS_BASE_URL", tools_base_url)) if not v]
    if missing:
        print(f"error: 未設定: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)
    extra_env = {}
    for item in args.env:
        key, sep, value = item.partition("=")
        if not sep or not key:
            print(f"error: --env は KEY=VALUE 形式: {item!r}", file=sys.stderr)
            sys.exit(2)
        extra_env[key] = value

    agent_name = args.agent_name or DEFAULT_AGENT_NAMES[args.mode]
    try:
        definition_kwargs = hosted_agent_definition_kwargs(
            project_endpoint=project_endpoint,
            model=model,
            tools_base_url=tools_base_url,
            mode=args.mode,
            cpu=args.cpu,
            memory=args.memory,
            extra_env=extra_env,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    with tempfile.TemporaryDirectory(prefix="delegated-access-hosted-") as tmp:
        staged = stage_hosted_agent_dir(Path(tmp) / "staged")
        zip_path = create_code_zip(staged, Path(tmp) / f"{agent_name}.zip")
        files = sorted(str(p.relative_to(staged)) for p in staged.rglob("*") if p.is_file())
        print(f"zip: {len(files)} files", file=sys.stderr)
        for name in files:
            print(f"  {name}", file=sys.stderr)
        print(json.dumps({"agent_name": agent_name, **definition_kwargs}, indent=2,
                         ensure_ascii=False))
        responses_url = agent_responses_url(project_endpoint, agent_name)
        if not args.apply:
            print("[dry-run] 送信していない。--apply でデプロイする", file=sys.stderr)
            print(f"AGENT_RESPONSES_URL={responses_url}")
            return
        _deploy(project_endpoint, agent_name, definition_kwargs, zip_path, args.timeout)
    print(f"AGENT_RESPONSES_URL={responses_url}")


def _deploy(project_endpoint: str, agent_name: str, definition_kwargs: dict, zip_path: Path,
            timeout: float) -> None:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    with (
        zip_path.open("rb") as code_stream,
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=project_endpoint, credential=credential) as project,
    ):
        created = project.agents.create_version_from_code(
            agent_name=agent_name,
            description="Delegated-access agent (Port 15): per-user MCP tools via OBO forwarding.",
            definition=build_definition(definition_kwargs),
            code=code_stream,
        )
        print(f"created version {created.version} — provisioning...", file=sys.stderr)
        deadline = time.monotonic() + timeout
        while True:
            details = project.agents.get_version(agent_name=agent_name, agent_version=created.version)
            status = details["status"]
            print(f"  status={status}", file=sys.stderr)
            if status == "active":
                break
            if status == "failed":
                raise RuntimeError(f"provisioning failed: {dict(details)}")
            if time.monotonic() > deadline:
                raise RuntimeError(f"provisioning timeout({timeout:.0f}s)")
            time.sleep(POLL_INTERVAL_SECONDS)

        # hosted agent は 1 バージョン 100% のみ(トラフィック分割不可)
        project.agents.update_details(
            agent_name=agent_name, agent_endpoint=route_all_traffic(created.version)
        )
        print(f"routed 100% -> version {created.version}", file=sys.stderr)


if __name__ == "__main__":
    main()
