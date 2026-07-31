"""hosted agent エントリポイント(Foundry Agent Service / Responses protocol 2.0.0)。

foundry-samples の hosted-agents/agent-framework/responses/01-basic の main.py
規約に従う: このファイルがデプロイ zip のルートに置かれ、コンテナは
``python main.py`` で起動して :8088 で Responses API を待ち受ける
(``ResponsesHostServer`` が HTTP サーバー・ヘルスチェック・OTel を担う)。

クライアント実行(CLI)との差分 — README の学びの実体:

- モデル呼び出しは **FoundryChatClient + DefaultAzureCredential**。コンテナには
  デプロイ時に agent identity(専用 Entra ID)が付与されるため **API キーを
  一切持ち込まない**(CLI は OpenAI v1 エンドポイント+キー)
- トレーシングの配線コードなし: App Insights 接続文字列はプラットフォームが
  自動注入し、protocol ライブラリが OTel を既定発信する
- HN 収集はエージェント内部の httpx 関数ツール(hosted.py)。エージェント
  定義にツールを直付けできない制約は Foundry 管理ツールの話で、ここには
  該当しない(設計判断は hosted.py の docstring)

ローカル実行(デプロイ前の検証):

    uv sync --extra dev --extra hosting
    FOUNDRY_PROJECT_ENDPOINT=... FOUNDRY_MODEL_NAME=... uv run python hosting/main.py
    curl -sS -H "Content-Type: application/json" -X POST \
        http://localhost:8088/responses -d '{"input": "today's brief", "stream": false}'
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# zip デプロイでは hn_briefing_maf/ が main.py と同じルートに同梱される。
# リポジトリから直接 `python hosting/main.py` するとき用に src/ もフォールバック。
try:
    import hn_briefing_maf  # noqa: F401
except ImportError:  # pragma: no cover - ローカル実行のみの経路
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential

from hn_briefing_maf.hn import default_http_client
from hn_briefing_maf.hosted import build_hosted_briefing_agent


def main() -> None:
    from agent_framework.foundry import FoundryChatClient

    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME") or os.environ["FOUNDRY_MODEL_NAME"]

    chat_client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=model,
        credential=DefaultAzureCredential(),
    )
    agent = build_hosted_briefing_agent(chat_client, default_http_client())
    ResponsesHostServer(agent).run()


if __name__ == "__main__":
    main()
