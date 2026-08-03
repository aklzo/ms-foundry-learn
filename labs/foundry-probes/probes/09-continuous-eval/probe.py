"""継続評価(continuous evaluation / evaluation_rules)の挙動確認。

critique-loop は evals API の「その場でランを作る」バッチ評価を検証済み。
未検証なのは **evaluation_rules によるイベント駆動の自動評価**:
response_completed イベントで自動的に評価ランが作られる仕組み。

観点:
  A. eval 定義(builtin.coherence)の作成
  B. evaluation_rules.create_or_update(RESPONSE_COMPLETED + CONTINUOUS_EVALUATION)
  C. ルールが list に現れるか・フィールドの見え方
  D. store=True の response を数件生成 → 自動ランが作られるか(バウンドポーリング)
  E. 後片付け

注意: 自動ランは非同期。observ できなくても「配線の仕方と観測可否」自体が記録価値。
"""

from __future__ import annotations

import sys
import time

from foundry_probes.common import Settings, make_project_client, section, show

EVAL_NAME = "probe-coherence-eval"
RULE_ID = "probe-continuous-rule"
AGENT_NAME = "probe-ce-agent"


def main() -> int:
    settings = Settings.from_env()
    project = make_project_client(settings)
    client = project.get_openai_client()

    section("0. 継続評価の対象となる prompt agent を用意(filter.agent_name 用)")
    from azure.ai.projects.models import PromptAgentDefinition

    project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=PromptAgentDefinition(
            model=settings.model,
            instructions="質問に簡潔に答えるアシスタント。",
        ),
    )
    agent_client = project.get_openai_client(agent_name=AGENT_NAME)
    print(f"  agent 準備完了: {AGENT_NAME}")

    section("A. eval 定義の作成(builtin.coherence)")
    try:
        ev = client.evals.create(
            name=EVAL_NAME,
            data_source_config={
                "type": "custom",
                "item_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "response": {"type": "string"}},
                    "required": ["query", "response"],
                },
                "include_sample_schema": False,
            },
            testing_criteria=[
                {
                    "type": "azure_ai_evaluator",
                    "name": "coherence",
                    "evaluator_name": "builtin.coherence",
                    "initialization_parameters": {"deployment_name": settings.model},
                    "data_mapping": {"query": "{{item.query}}", "response": "{{item.response}}"},
                }
            ],
        )
        show("eval 作成", {"id": ev.id, "name": ev.name})
        eval_id = ev.id
    except Exception as exc:
        print(f"!! eval 作成失敗: {type(exc).__name__}: {str(exc)[:400]}")
        return 1

    section("B. evaluation_rules.create_or_update(RESPONSE_COMPLETED 駆動)")
    from azure.ai.projects.models import (
        ContinuousEvaluationRuleAction,
        EvaluationRule,
        EvaluationRuleEventType,
        EvaluationRuleFilter,
    )

    try:
        rule = project.evaluation_rules.create_or_update(
            id=RULE_ID,
            evaluation_rule=EvaluationRule(
                display_name="probe continuous coherence",
                description="probe: response_completed で coherence を自動評価",
                event_type=EvaluationRuleEventType.RESPONSE_COMPLETED,
                enabled=True,
                filter=EvaluationRuleFilter(agent_name=AGENT_NAME),
                action=ContinuousEvaluationRuleAction(
                    eval_id=eval_id,
                    max_hourly_runs=100,
                    sampling_rate=1.0,
                ),
            ),
        )
        show("ルール作成", rule.as_dict())
    except Exception as exc:
        print(f"!! ルール作成失敗: {type(exc).__name__}: {str(exc)[:500]}")

    section("C. ルール一覧")
    try:
        for r in project.evaluation_rules.list():
            d = r.as_dict()
            print(f"  id={d.get('id')} event={d.get('event_type')} enabled={d.get('enabled')} action={d.get('action',{}).get('type')}")
    except Exception as exc:
        print(f"!! list 失敗: {type(exc).__name__}: {str(exc)[:200]}")

    section("D. agent 経由で response を生成 → 自動ラン発火の観測")
    for i in range(3):
        r = agent_client.responses.create(
            input=f"継続評価テスト{i}: 再帰関数を一文で説明して。",
            store=True,
        )
        print(f"  response {i} 生成: {r.id}")
    print("  自動ラン発火をポーリング(最大 120s)...")
    t0 = time.monotonic()
    seen_runs: list[str] = []
    while time.monotonic() - t0 < 120:
        try:
            runs = list(client.evals.runs.list(eval_id))
            if runs:
                for run in runs:
                    if run.id not in seen_runs:
                        seen_runs.append(run.id)
                        print(f"  {time.monotonic()-t0:5.1f}s 自動ラン検出: {run.id} status={run.status}")
                break
        except Exception as exc:
            print(f"  runs.list エラー: {type(exc).__name__}: {str(exc)[:150]}")
            break
        time.sleep(10)
    if not seen_runs:
        print(f"  {time.monotonic()-t0:5.1f}s 自動ランは観測されず(非同期遅延 or 別サーフェス集計の可能性)")

    section("E. 後片付け")
    try:
        project.evaluation_rules.delete(RULE_ID)
        print("  ルール削除 OK")
    except Exception as exc:
        print(f"!! ルール削除: {type(exc).__name__}: {str(exc)[:150]}")
    try:
        client.evals.delete(eval_id)
        print("  eval 削除 OK")
    except Exception as exc:
        print(f"!! eval 削除: {type(exc).__name__}: {str(exc)[:150]}")
    try:
        project.agents.delete(agent_name=AGENT_NAME)
        print("  agent 削除 OK")
    except Exception as exc:
        print(f"!! agent 削除: {type(exc).__name__}: {str(exc)[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
