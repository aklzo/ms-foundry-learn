"""hosted agent の版更新をまたいで会話を続けられるか(2026-09-30 新設)。

本番で hosted agent の新しい版をデプロイしたとき、旧版で始まった会話を続けられるかを
確かめる。公式(manage-hosted-sessions 2026-08-21 版)は「セッション(サンドボックス)は
作成時に 1 つの版に固定される」「会話の続きは previous_response_id か conversation で、
セッション ID とは別」と書いており、**会話のつなぎ方によって版更新後の挙動が変わりうる**。

会話のつなぎ方 3 通り × 版の操作 5 段階を観察する:

  P = previous_response_id だけ(セッション ID は渡さない。Port 15 の中間層と同じ)
  S = previous_response_id + agent_session_id(サンドボックスの $HOME も引き継ぐ)
  C = conversation ID(公式: 会話に安定したセッションが自動で結び付く)

  1. v1 にルーティングして 3 本の会話を 2 ターンずつ始める
  2. v2 をデプロイして 100% を v2 に向ける → 3 本を続ける(+ v2 で新しい会話 N)
     移行の試み: v2 に固定した新しいセッションで S / C を続ける
  3. ロールバック: 100% を v1 に戻す → v2 で始めた N を続ける → v2 に戻す
  4. v1 の版を削除する → 3 本を続ける
  5. 休止: idle_timeout(120 秒)を超えて待ち、v3 をデプロイして 100% を v3 に向ける →
     暗黙に作られたセッション(P / N)と、v2 に明示固定したセッション(S / C の移行先)を再開する

検証用エージェント(agent/main.py)はモデルを呼ばず、応答した版・セッション・受け取った
履歴・$HOME のマーカー・コンテナの起動時刻を JSON で返す。idle_timeout は 120 秒。
2026-09-30 の実測結果と解釈は NOTES.md(5 は当日 3 回に分けて実行した内容を 1 本にまとめたもの)。

前提: az login 済み・Foundry User(agents/write)・FOUNDRY_PROJECT_ENDPOINT
(infra.bicep の出力。環境変数が lab の .env より優先)。課金は hosted agent の
セッション中の CPU / メモリだけ(モデルは呼ばない)。

    uv run python probes/10-hosted-version-continuity/probe.py 2>&1 | tee logs/10-hosted-version-continuity.log
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from foundry_probes.common import LAB_ROOT, section, show

PROBE_DIR = Path(__file__).resolve().parent
AGENT_DIR = PROBE_DIR / "agent"
AGENT_NAME = "probe-version-continuity"
IDLE_TIMEOUT_SECONDS = 120
RESULT_PATH = LAB_ROOT / "logs" / "10-hosted-version-continuity.json"

records: list[dict[str, Any]] = []


def _zip_agent(tmp: Path) -> Path:
    zip_path = tmp / "agent.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("main.py", "requirements.txt"):
            zf.write(AGENT_DIR / name, name)
    return zip_path


def deploy(project: Any, build: str) -> str:
    """検証用エージェントの新しい版を作り、active になるまで待つ(ルーティングは別)。"""
    from azure.ai.projects.models import (
        CodeConfiguration,
        CodeDependencyResolution,
        HostedAgentDefinition,
        ProtocolVersionRecord,
        SessionConfiguration,
    )

    definition = HostedAgentDefinition(
        cpu="0.5",
        memory="1Gi",
        code_configuration=CodeConfiguration(
            runtime="python_3_13",
            entry_point=["python", "main.py"],
            dependency_resolution=CodeDependencyResolution.REMOTE_BUILD,
        ),
        environment_variables={"PROBE_BUILD": build},
        protocol_versions=[ProtocolVersionRecord(protocol="responses", version="2.0.0")],
        session_configuration=SessionConfiguration(idle_timeout_seconds=IDLE_TIMEOUT_SECONDS),
    )
    with tempfile.TemporaryDirectory() as tmp, _zip_agent(Path(tmp)).open("rb") as code:
        created = project.agents.create_version_from_code(
            agent_name=AGENT_NAME,
            definition=definition,
            code=code,
            description=f"probe 10 build {build}",
        )
    version = created.version
    started = time.monotonic()
    while True:
        details = project.agents.get_version(agent_name=AGENT_NAME, agent_version=version)
        status = details["status"]
        if status == "active":
            break
        if status == "failed":
            show("provisioning failed", dict(details))
            raise SystemExit(1)
        if time.monotonic() - started > 900:
            raise SystemExit("provisioning timeout")
        time.sleep(10)
    print(f"  build={build} -> version {version} active ({time.monotonic() - started:.0f}s)")
    return version


def route(project: Any, version: str) -> None:
    from azure.ai.projects.models import (
        AgentEndpointConfig,
        FixedRatioVersionSelectionRule,
        ProtocolConfiguration,
        ResponsesProtocolConfiguration,
        VersionSelector,
    )

    project.agents.update_details(
        agent_name=AGENT_NAME,
        agent_endpoint=AgentEndpointConfig(
            version_selector=VersionSelector(
                version_selection_rules=[
                    FixedRatioVersionSelectionRule(agent_version=version, traffic_percentage=100)
                ]
            ),
            protocol_configuration=ProtocolConfiguration(responses=ResponsesProtocolConfiguration()),
        ),
    )
    print(f"  routed 100% -> version {version}")


def ask(
    client: Any,
    label: str,
    text: str,
    *,
    prev: str | None = None,
    session: str | None = None,
    conversation: str | None = None,
) -> dict[str, Any]:
    """1 ターン送って、応答した版・履歴・セッションを記録する(失敗も記録)。"""
    extra: dict[str, Any] = {}
    if session:
        extra["agent_session_id"] = session
    if conversation:
        extra["conversation"] = conversation
    kwargs: dict[str, Any] = {"input": text, "store": True}
    if prev:
        kwargs["previous_response_id"] = prev
    if extra:
        kwargs["extra_body"] = extra
    sent = {"prev": prev, "session": session, "conversation": conversation}
    started = time.monotonic()
    try:
        resp = client.responses.create(**kwargs)
    except Exception as ex:
        rec = {
            "label": label,
            "ok": False,
            "sent": sent,
            "status_code": getattr(ex, "status_code", None),
            "error": str(getattr(ex, "body", None) or ex)[:600],
            "elapsed_s": round(time.monotonic() - started, 1),
        }
        records.append(rec)
        print(f"  [{label}] ERROR {rec['status_code']}: {rec['error'][:300]}")
        return rec
    extra_fields = dict(resp.model_extra or {})
    try:
        report = json.loads(resp.output_text)
    except Exception:
        report = {"raw": (resp.output_text or "")[:300]}
    history = report.get("history") or []
    first_user = next((h.get("text") for h in history if h.get("role") == "user"), None)
    rec = {
        "label": label,
        "ok": True,
        "sent": sent,
        "response_id": resp.id,
        "status": resp.status,
        "agent_session_id": extra_fields.get("agent_session_id"),
        "extra_keys": sorted(extra_fields),
        "agent_reference": extra_fields.get("agent_reference"),
        "build": report.get("build"),
        "agent_version_env": report.get("agent_version_env"),
        "session_env": report.get("session_env"),
        "history_count": report.get("history_count"),
        "history_first_user": first_user,
        "history_error": report.get("history_error"),
        "marker_before": report.get("marker_before"),
        "appinsights_env_present": report.get("appinsights_env_present"),
        "container_started_at": report.get("container_started_at"),
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    records.append(rec)
    print(
        f"  [{label}] build={rec['build']} v{rec['agent_version_env']} "
        f"session={str(rec['agent_session_id'])[:12]} history={rec['history_count']} "
        f"first_user={rec['history_first_user']!r} marker={rec['marker_before']} "
        f"history_error={rec['history_error']} ({rec['elapsed_s']}s)"
    )
    return rec


def list_sessions(project: Any, title: str) -> None:
    try:
        items = [s.as_dict() for s in project.agents.list_sessions(agent_name=AGENT_NAME)]
    except Exception as ex:
        print(f"  list_sessions failed: {ex}")
        return
    records.append({"label": f"sessions:{title}", "sessions": items})
    show(f"sessions ({title})", items, limit=2500)


def main() -> int:
    load_dotenv(LAB_ROOT / ".env")  # 既存の環境変数は上書きしない
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    if not endpoint:
        print("FOUNDRY_PROJECT_ENDPOINT が未設定(infra.bicep の出力 projectEndpoint)", file=sys.stderr)
        return 2
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

    section("1. v1 をデプロイして 3 通りのつなぎ方で会話を始める")
    v1 = deploy(project, "v1")
    route(project, v1)
    client = project.get_openai_client(agent_name=AGENT_NAME)
    p1 = ask(client, "P1@v1", "P: 好きな果物はりんご")
    p2 = ask(client, "P2@v1", "P: 覚えている?", prev=p1.get("response_id"))
    s1 = ask(client, "S1@v1", "S: 好きな果物はみかん")
    s_session = s1.get("agent_session_id")
    s2 = ask(client, "S2@v1", "S: 覚えている?", prev=s1.get("response_id"), session=s_session)
    conv = client.conversations.create()
    print(f"  conversation {conv.id}")
    ask(client, "C1@v1", "C: 好きな果物はもも", conversation=conv.id)
    ask(client, "C2@v1", "C: 覚えている?", conversation=conv.id)
    list_sessions(project, "after v1 turns")

    section("2. v2 をデプロイして 100% を v2 に向け、同じ会話を続ける")
    v2 = deploy(project, "v2")
    route(project, v2)
    p3 = ask(client, "P3@route-v2", "P: まだ覚えている?", prev=p2.get("response_id"))
    s3 = ask(client, "S3@route-v2", "S: まだ覚えている?", prev=s2.get("response_id"), session=s_session)
    ask(client, "C3@route-v2", "C: まだ覚えている?", conversation=conv.id)
    n1 = ask(client, "N1@route-v2", "N: 好きな果物はぶどう")

    section("2b. 移行の試み: v2 に固定した新しいセッションで S / C を続ける")
    from azure.ai.projects.models import VersionRefIndicator

    migrated: dict[str, str | None] = {}
    for key in ("S", "C"):
        try:
            session = project.agents.create_session(
                agent_name=AGENT_NAME, version_indicator=VersionRefIndicator(agent_version=v2)
            )
            migrated[key] = session.agent_session_id
            show(f"create_session pinned v{v2} for {key}", session.as_dict(), limit=600)
        except Exception as ex:
            migrated[key] = None
            print(f"  create_session failed for {key}: {ex}")
    if migrated.get("S"):
        ask(client, "S-mig@v2session", "S: 新しいセッションでも覚えている?",
            prev=s3.get("response_id") or s2.get("response_id"), session=migrated["S"])
    if migrated.get("C"):
        ask(client, "C-mig@v2session", "C: 新しいセッションでも覚えている?",
            conversation=conv.id, session=migrated["C"])
    list_sessions(project, "after routing to v2")

    section("3. ロールバック: 100% を v1 に戻して、v2 で始めた会話 N を続ける")
    route(project, v1)
    ask(client, "N2@route-v1", "N: 覚えている?", prev=n1.get("response_id"))
    route(project, v2)

    section("4. v1 の版を削除して、3 通りの会話を続ける")
    try:
        result = project.agents.delete_version(agent_name=AGENT_NAME, agent_version=v1)
        show("delete_version(v1)", result.as_dict() if hasattr(result, "as_dict") else result)
        records.append({"label": "delete_v1", "ok": True})
    except Exception as ex:
        print(f"  delete_version(v1) failed: {getattr(ex, 'status_code', '')} {str(ex)[:400]}")
        records.append({"label": "delete_v1", "ok": False, "error": str(ex)[:400]})
        try:
            project.agents.delete_version(agent_name=AGENT_NAME, agent_version=v1, force=True)
            print("  delete_version(v1, force=True) ok")
            records.append({"label": "delete_v1_force", "ok": True})
        except Exception as ex2:
            print(f"  delete_version(v1, force=True) failed: {str(ex2)[:400]}")
            records.append({"label": "delete_v1_force", "ok": False, "error": str(ex2)[:400]})
    time.sleep(20)
    p4 = ask(client, "P4@v1-deleted", "P: 版を消した後も覚えている?", prev=p3.get("response_id"))
    ask(client, "S4@v1-deleted", "S: 版を消した後も覚えている?",
        prev=s3.get("response_id") or s2.get("response_id"), session=s_session)
    ask(client, "C4@v1-deleted", "C: 版を消した後も覚えている?", conversation=conv.id)
    list_sessions(project, "after deleting v1")

    section("5. 休止したセッションを、v3 に切り替えた後に再開する")
    wait = IDLE_TIMEOUT_SECONDS + 60
    print(f"  {wait} 秒待って全セッションを休止させる(idle_timeout {IDLE_TIMEOUT_SECONDS} 秒)")
    time.sleep(wait)
    list_sessions(project, "after idle wait")
    v3 = deploy(project, "v3")
    route(project, v3)
    ask(client, "P5@route-v3(idle)", "P: 休止明けでも覚えている?", prev=p4.get("response_id"))
    ask(client, "N3@route-v3(idle)", "N: 休止明けでも覚えている?", prev=n1.get("response_id"))
    if migrated.get("S"):
        ask(client, "Smig2@route-v3(pinned-v2)", "S: 休止明け(v2 固定セッション)",
            prev=s3.get("response_id") or s2.get("response_id"), session=migrated["S"])
    if migrated.get("C"):
        ask(client, "Cmig2@route-v3(pinned-v2)", "C: 休止明け(v2 固定セッション)",
            conversation=conv.id, session=migrated["C"])
    list_sessions(project, "after resuming on v3")

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps({"v1": v1, "v2": v2, "v3": v3, "records": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    section("まとめ")
    for rec in records:
        if "build" in rec or not rec.get("ok", True):
            print(
                f"  {rec['label']:<26} ok={rec.get('ok')} build={rec.get('build')} "
                f"history={rec.get('history_count')} status={rec.get('status_code', '')}"
            )
    print(f"  詳細: {RESULT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
