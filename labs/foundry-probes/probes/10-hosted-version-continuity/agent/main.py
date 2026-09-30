"""probe 10 の検証用 hosted agent(Responses protocol 2.0.0)。モデルは呼ばない。

受け取ったリクエストについて「どの版のコンテナが・どのセッションで・どれだけの履歴を
受け取ったか」を JSON で返すだけのエージェント。版更新の前後で同じ会話を続けたときに、
どの版が応答したか(``build`` / ``agent_version_env``)、会話履歴が引き継がれたか
(``history_count`` / ``history``)、セッションのファイル(``$HOME``)が残ったか
(``marker_before``)を観察する。

- ``PROBE_BUILD`` は版ごとに変える環境変数(v1 / v2)。コードは同じでも、版ごとに
  環境変数が固定されるので「どの版が応答したか」の目印になる
- ``$HOME/probe-marker.txt`` に 1 行ずつ追記する。同じセッション(サンドボックス)に
  戻ってきたときだけ前の行が見える
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from azure.ai.agentserver.core import get_request_context
from azure.ai.agentserver.responses import ResponsesAgentServerHost, TextResponse

BUILD = os.environ.get("PROBE_BUILD", "unknown")
STARTED_AT = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
MARKER = "probe-marker.txt"

app = ResponsesAgentServerHost()


def _as_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "as_dict"):
        return item.as_dict()
    return {"repr": repr(item)[:200]}


def _summary(item: Any) -> dict[str, Any]:
    data = _as_dict(item)
    texts = [
        str(part.get("text", ""))[:60]
        for part in data.get("content") or []
        if isinstance(part, dict) and part.get("text")
    ]
    return {"type": data.get("type"), "role": data.get("role"), "text": " / ".join(texts)[:120]}


@app.response_handler
async def handler(request, context, cancellation_signal):
    user_input = await context.get_input_text() or ""
    try:
        history = [_summary(item) for item in await context.get_history()]
        history_error = None
    except Exception as ex:
        history = []
        history_error = f"{type(ex).__name__}: {str(ex)[:300]}"

    marker = Path(os.environ.get("HOME", "/tmp")) / MARKER
    try:
        before = marker.read_text(encoding="utf-8").splitlines() if marker.exists() else []
        with marker.open("a", encoding="utf-8") as f:
            f.write(f"{BUILD}|v{os.environ.get('FOUNDRY_AGENT_VERSION')}|{user_input[:24]}\n")
        marker_error = None
    except Exception as ex:
        before = []
        marker_error = f"{type(ex).__name__}: {str(ex)[:200]}"

    ctx = get_request_context()
    report = {
        "build": BUILD,
        "agent_version_env": os.environ.get("FOUNDRY_AGENT_VERSION"),
        "session_env": os.environ.get("FOUNDRY_AGENT_SESSION_ID"),
        "session_ctx": ctx.session_id,
        "conversation_chain_id": getattr(context, "conversation_chain_id", None),
        "history_count": len(history),
        "history": history,
        "history_error": history_error,
        "marker_before": before,
        "marker_error": marker_error,
        "appinsights_env_present": bool(os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")),
        "container_started_at": STARTED_AT,
        "input": user_input[:60],
    }
    return TextResponse(context, request, text=json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    app.run()
