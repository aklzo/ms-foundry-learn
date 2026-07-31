"""hosted agent のデプロイ(SDK 経路・ライブ専用)。

    uv sync --extra dev --extra hosting
    az login   # Foundry Project Manager 以上のロールが必要
    uv run python hosting/deploy_hosted_agent.py                 # デプロイ+100% ルーティング
    uv run python hosting/deploy_hosted_agent.py --invoke "Give me today's brief."
    uv run python hosting/deploy_hosted_agent.py --dry-run       # zip 内容と定義の確認のみ

経路(実装前調査 quickstart-hosted-agent の Python SDK パス):
``AIProjectClient.agents.create_version_from_code`` に zip(ルートに main.py /
requirements.txt / hn_briefing_maf/)+ HostedAgentDefinition を渡す →
provisioning をポーリング → ``update_details`` でエンドポイントを新バージョン
100% に向ける(hosted agent はトラフィック分割不可・常に 1 バージョン 100%)。
quickstart は検証後にバージョンを削除するが、本ポートは **Routine が呼ぶ
常設エージェント**なので残す。

azd 代替: `azd ai agent init` → `azd provision` → `azd deploy`(azure.yaml
一式を azd が管理)。既存の共有基盤へ載せる本ラボの流儀では SDK 経路の方が
Bicep + スクリプトの 2 段デプロイ規約に馴染む(README 参照)。

Bicep との関係: エージェント本体/バージョンはデータプレーンのオブジェクトで
ARM では作れない(infra/main.bicep のコメント参照)。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

PORT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT_ROOT / "src"))

from hn_briefing_maf.config import ConfigError, FoundrySettings
from hn_briefing_maf.hosting_setup import (
    create_code_zip,
    hosted_agent_definition_kwargs,
    stage_hosted_agent_dir,
)

POLL_INTERVAL_SECONDS = 10.0


def main() -> None:
    parser = argparse.ArgumentParser(description="hn-briefing hosted agent のデプロイ")
    parser.add_argument("--agent-name", default=None, help="hosted agent 名(既定は設定値)")
    parser.add_argument("--cpu", default="0.5", help="サンドボックス vCPU(0.5/1/2)")
    parser.add_argument("--memory", default="1Gi", help="サンドボックスメモリ(1Gi/2Gi/4Gi)")
    parser.add_argument("--invoke", default=None, help="デプロイ後にこのプロンプトで 1 回呼ぶ")
    parser.add_argument("--timeout", type=float, default=600.0, help="provisioning 待ち上限秒")
    parser.add_argument(
        "--dry-run", action="store_true", help="zip 内容と定義を表示するだけ(送信しない)"
    )
    args = parser.parse_args()

    try:
        settings = FoundrySettings.from_env()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    if not settings.project_endpoint:
        print(
            "error: FOUNDRY_PROJECT_ENDPOINT が未設定(hosted agent のデプロイは"
            "プロジェクトエンドポイント+Entra ID が必要。labs/maf-ports/.env を確認)",
            file=sys.stderr,
        )
        sys.exit(2)
    agent_name = args.agent_name or settings.agent_name
    definition_kwargs = hosted_agent_definition_kwargs(
        project_endpoint=settings.project_endpoint,
        model=settings.model,
        cpu=args.cpu,
        memory=args.memory,
    )

    with tempfile.TemporaryDirectory(prefix="hn-briefing-hosted-") as tmp:
        staged = stage_hosted_agent_dir(Path(tmp) / "staged")
        zip_path = create_code_zip(staged, Path(tmp) / f"{agent_name}.zip")
        files = sorted(str(p.relative_to(staged)) for p in staged.rglob("*") if p.is_file())
        print(f"zip: {len(files)} files — {', '.join(files[:6])} ...", file=sys.stderr)

        if args.dry_run:
            print(json.dumps({"agent_name": agent_name, **definition_kwargs}, indent=2))
            return
        _deploy(settings, agent_name, definition_kwargs, zip_path, args)


def _deploy(settings, agent_name: str, definition_kwargs: dict, zip_path: Path, args) -> None:
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        AgentEndpointConfig,
        CodeConfiguration,
        CodeDependencyResolution,
        FixedRatioVersionSelectionRule,
        HostedAgentDefinition,
        ProtocolConfiguration,
        ProtocolVersionRecord,
        ResponsesProtocolConfiguration,
        VersionSelector,
    )
    from azure.identity import DefaultAzureCredential

    definition = HostedAgentDefinition(
        cpu=definition_kwargs["cpu"],
        memory=definition_kwargs["memory"],
        code_configuration=CodeConfiguration(
            runtime=definition_kwargs["runtime"],
            entry_point=definition_kwargs["entry_point"],
            dependency_resolution=CodeDependencyResolution.REMOTE_BUILD,
        ),
        environment_variables=definition_kwargs["environment_variables"],
        protocol_versions=[
            ProtocolVersionRecord(protocol=protocol, version=version)
            for protocol, version in definition_kwargs["protocols"]
        ],
    )

    with (
        zip_path.open("rb") as code_stream,
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=settings.project_endpoint, credential=credential) as project,
    ):
        created = project.agents.create_version_from_code(
            agent_name=agent_name,
            description=(
                "Always-on HN briefing agent (MAF port of always_on_hn_briefing_agent)."
            ),
            definition=definition,
            code=code_stream,
        )
        print(f"created version {created.version} — provisioning...", file=sys.stderr)

        deadline = time.monotonic() + args.timeout
        while True:
            details = project.agents.get_version(
                agent_name=agent_name, agent_version=created.version
            )
            status = details["status"]
            print(f"  status={status}", file=sys.stderr)
            if status == "active":
                break
            if status == "failed":
                raise RuntimeError(f"provisioning failed: {dict(details)}")
            if time.monotonic() > deadline:
                raise RuntimeError(f"provisioning timeout({args.timeout:.0f}s)")
            time.sleep(POLL_INTERVAL_SECONDS)

        # 常設運用: エンドポイントを新バージョン 100% に向けたまま残す
        # (hosted agent は 1 バージョン 100% のみ・分割不可)
        project.agents.update_details(
            agent_name=agent_name,
            agent_endpoint=AgentEndpointConfig(
                version_selector=VersionSelector(
                    version_selection_rules=[
                        FixedRatioVersionSelectionRule(
                            agent_version=created.version, traffic_percentage=100
                        )
                    ]
                ),
                protocol_configuration=ProtocolConfiguration(
                    responses=ResponsesProtocolConfiguration()
                ),
            ),
        )
        endpoint = project.agents.get(agent_name=agent_name).agent_endpoint
        print(f"routed 100% -> version {created.version}", file=sys.stderr)
        print(f"agent endpoint: {endpoint}")

        if args.invoke:
            with project.get_openai_client(agent_name=agent_name) as openai_client:
                response = openai_client.responses.create(input=args.invoke)
            print(response.output_text)


if __name__ == "__main__":
    main()
