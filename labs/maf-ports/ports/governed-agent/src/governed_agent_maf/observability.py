"""Foundry トレーシング(App Insights 送信)の配線。

agent-framework は既定で OTel 計装が有効。エクスポータだけ App Insights に
向ければ、エージェント実行(invoke_agent)・ツール実行(execute_tool)が
トレースとしてポータルに届く。**自前の監査連鎖(audit.py)とは役割が別**:
トレースは内容の追跡・調査、監査連鎖は順序と非改ざんの証明(README 学び 4)。
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
