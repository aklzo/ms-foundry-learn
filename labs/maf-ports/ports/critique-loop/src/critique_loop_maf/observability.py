"""Foundry トレーシング(App Insights 送信)の配線。

agent-framework は既定で OTel 計装が有効。エクスポータだけ App Insights に
向ければ、エージェント実行(invoke_agent)とワークフローのノード実行
(executor.process — ループの周回数がスパン数でそのまま見える)がトレース
としてポータル(プロジェクトの Traces / App Insights)に届く。

パターンは agent_framework.observability の公式 docstring どおり:
``configure_azure_monitor(connection_string=...)`` を先に呼ぶ。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def setup_tracing(connection_string: str | None) -> bool:
    """App Insights へのトレース送信を構成する。

    接続文字列が無い、または azure-monitor-opentelemetry 未インストール
    (オフライン実行)の場合は何もしない。戻り値は有効化されたかどうか。
    """
    if not connection_string:
        return False
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        logger.warning(
            "azure-monitor-opentelemetry が未インストールのためトレース無効"
            "(uv sync --extra live で導入)"
        )
        return False
    configure_azure_monitor(connection_string=connection_string)
    return True
