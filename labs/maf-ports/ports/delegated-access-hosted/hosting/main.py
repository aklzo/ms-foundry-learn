"""hosted agent エントリポイント(Foundry Agent Service / Responses protocol 2.0.0)。

デプロイ zip のルートに置かれ、コンテナは ``python main.py`` で起動して :8088
(``PORT``)で Responses API を待ち受ける。zip = このファイル + ``requirements.txt`` +
``delegated_access_maf/`` パッケージ。

Port 11(hn-briefing-hosted)との違い — このポートの本題:

- MAF の ``ResponsesHostServer`` を**使わない**。あれはエージェントと MCP ツールを起動時に
  1 回だけ接続し、リクエストのヘッダー(``x-client-*``)をツールへ渡さない。代わりに
  Agent Server SDK の ``ResponsesAgentServerHost`` にハンドラーを直接登録し、
  リクエストごとに「委任トークンを読む → MCP サーバーの見え方を確かめる → 見えた
  ツールだけで MAF Agent を作る」(``delegated_access_maf.agent``)
- 共有するのはモデル用の ``FoundryChatClient``(エージェント自身の ID =
  ``DefaultAzureCredential``)だけ。利用者のトークンはモデルに渡らない
- resilient / durable background モードは有効にしない(``client_headers`` = 委任トークンが
  復旧用に永続化される)。``build_host`` が有効化を検出したら起動を拒否する
- GenAI のメッセージ内容のトレース記録を既定で切る
  (``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false``)。SDK は未設定だと
  「記録する」扱いで、利用者ごとに見えた文書の中身やツール引数が App Insights に残る

必要な環境変数: ``TOOLS_BASE_URL``(APIM ゲートウェイ or ツールサーバー)/
``FOUNDRY_PROJECT_ENDPOINT`` / ``FOUNDRY_MODEL_NAME``(``AZURE_AI_MODEL_DEPLOYMENT_NAME``
があれば優先)。

ローカル実行(デプロイ前の検証。中間層の ``AGENT_RESPONSES_URL`` を
``http://localhost:8088/responses`` にすると Foundry を通さずに届く):

    uv sync --extra dev --extra hosting
    az login     # モデル呼び出しは DefaultAzureCredential(ローカルでは開発者の ID)
    TOOLS_BASE_URL=https://<apim>.azure-api.net FOUNDRY_PROJECT_ENDPOINT=... \\
        FOUNDRY_MODEL_NAME=... uv run python hosting/main.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# zip デプロイでは delegated_access_maf/ が main.py と同じルートに同梱される。
# リポジトリから直接 `python hosting/main.py` するとき用に src/ もフォールバック。
try:
    import delegated_access_maf  # noqa: F401
except ImportError:  # pragma: no cover - ローカル実行のみの経路
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from delegated_access_maf.agent.host import build_host
from delegated_access_maf.agent.runtime import DelegatedAccessRuntime
from delegated_access_maf.agent.settings import AgentSettings
from delegated_access_maf.redaction import install_log_redaction

#: SDK は未設定を「記録する」(true)と読む。このポートでは利用者ごとの内容をトレースに残さない
CAPTURE_CONTENT_ENV = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"


def build_chat_client(settings: AgentSettings):
    """モデル呼び出し用のクライアント(エージェント自身の ID。キーは持ち込まない)。"""
    from agent_framework.foundry import FoundryChatClient
    from azure.identity import DefaultAzureCredential

    if not settings.project_endpoint or not settings.model:
        raise SystemExit(
            "FOUNDRY_PROJECT_ENDPOINT と FOUNDRY_MODEL_NAME(またはプラットフォーム注入の"
            "AZURE_AI_MODEL_DEPLOYMENT_NAME)が必要です"
        )
    return FoundryChatClient(
        project_endpoint=settings.project_endpoint,
        model=settings.model,
        credential=DefaultAzureCredential(),
    )


def main() -> None:
    if not os.environ.get("FOUNDRY_HOSTING_ENVIRONMENT"):  # pragma: no cover - ローカル実行のみ
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    # ホストの構築(= OTel の設定)より前に決める。明示的に true にした場合だけ記録される
    os.environ.setdefault(CAPTURE_CONTENT_ENV, "false")
    settings = AgentSettings.from_env()
    runtime = DelegatedAccessRuntime(chat_client=build_chat_client(settings), settings=settings)
    host = build_host(runtime)
    # ハンドラー(コンソール / Azure Monitor)は host の初期化で付くので、その後に付ける
    installed = install_log_redaction()
    logging.getLogger("delegated_access_maf.agent").info(
        "delegated-access agent ready: tools=%s, log redaction on %d handler(s)",
        settings.tools_base_url,
        installed,
    )
    host.run()


if __name__ == "__main__":
    main()
