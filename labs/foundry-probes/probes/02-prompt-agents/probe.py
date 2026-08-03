"""Prompt agents(サービス側エージェント定義+バージョニング)の挙動確認。

maf-ports はエージェント定義をすべてクライアント側(MAF Agent)で持っていた。
サービス側に定義を置く prompt agent(GA)の CRUD・バージョン挙動・呼び出しが
未検証だった。

観点:
  A. create_version の戻り(バージョン番号・フィールド)
  B. 定義更新 → 自動バージョンスナップショット(版番号の増え方)
  C. list / list_versions の見え方
  D. 呼び出し: get_openai_client(agent_name=...) + responses.create(model 指定なし)
  E. エージェント × conversation でサービス側フルループ(状態+定義とも server)
  F. function ツール付き定義 — function_call が誰に返るか(クライアント実行ループか)
  G. 呼び出し時の instructions 上書きの可否
  H. delete_version / delete の挙動(有効版の削除は?)
"""

from __future__ import annotations

import json
import sys

from foundry_probes.common import Settings, make_project_client, section, show

AGENT_NAME = "probe-prompt-agent"


def main() -> int:
    settings = Settings.from_env()
    project = make_project_client(settings)
    from azure.ai.projects.models import FunctionTool, PromptAgentDefinition

    section("A. create_version(初回作成)")
    v1 = project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=PromptAgentDefinition(
            model=settings.model,
            instructions="あなたは俳句職人です。何を聞かれても五七五の俳句だけで答えます。",
        ),
        description="probe: 初版",
    )
    show("create_version 戻り値", v1.as_dict())

    section("B. 定義更新 → バージョンの増え方")
    v2 = project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=PromptAgentDefinition(
            model=settings.model,
            instructions="あなたは川柳職人です。何を聞かれても川柳だけで答えます。",
        ),
        description="probe: 改訂版",
    )
    print(f"  v1.version={v1.version} -> v2.version={v2.version}")

    section("C. list / list_versions")
    for a in project.agents.list():
        d = a.as_dict()
        print(f"  agent name={d.get('name')} 現行版={json.dumps(d.get('versions', {}), ensure_ascii=False)}")
    for v in project.agents.list_versions(agent_name=AGENT_NAME):
        d = v.as_dict()
        print(f"  version={d.get('version')} desc={d.get('description')}")

    section("D. 呼び出し(agent_name バインドの openai client、model 指定なし)")
    agent_client = project.get_openai_client(agent_name=AGENT_NAME)
    r = agent_client.responses.create(input="今日の天気は?")
    show("output_text(川柳で返れば最新版が既定)", r.output_text)
    show("response.model(定義側モデルが使われるか)", r.model)

    section("E. エージェント × conversation(状態も定義もサービス側)")
    conv = agent_client.conversations.create()
    r1 = agent_client.responses.create(conversation=conv.id, input="私の名前は月見です。挨拶して。")
    show("turn1", r1.output_text)
    r2 = agent_client.responses.create(conversation=conv.id, input="私の名前を呼んで一句。")
    show("turn2(名前を覚えていれば会話状態もサービス側)", r2.output_text)
    agent_client.conversations.delete(conv.id)

    section("F. function ツール付き定義(function_call の返り先)")
    try:
        project.agents.create_version(
            agent_name=AGENT_NAME,
            definition=PromptAgentDefinition(
                model=settings.model,
                instructions="天気を聞かれたら get_weather ツールを使う。",
                tools=[
                    FunctionTool(
                        name="get_weather",
                        description="都市の現在の天気を返す",
                        parameters={
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    )
                ],
            ),
            description="probe: function ツール版",
        )
        r = agent_client.responses.create(input="東京の天気を教えて")
        for item in r.output:
            print(f"  output item type={item.type}")
        show("最終 output(function_call がクライアントに返るか)", r.output[-1].model_dump(), limit=600)
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {exc}")

    section("G. 呼び出し時の instructions 上書き")
    try:
        r = agent_client.responses.create(input="自己紹介して", instructions="あなたは海賊です。")
        show("instructions 上書き結果", r.output_text)
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {exc}")

    section("H. 後片付け(delete)と削除の挙動")
    try:
        project.agents.delete_version(agent_name=AGENT_NAME, agent_version=str(v1.version))
        print("  v1 削除 OK")
    except Exception as exc:
        print(f"!! delete_version(v1): {type(exc).__name__}: {exc}")
    try:
        project.agents.delete(agent_name=AGENT_NAME)
        print("  agent 削除 OK")
        remaining = [a.as_dict().get("name") for a in project.agents.list()]
        print(f"  削除後の list: {remaining}")
    except Exception as exc:
        print(f"!! delete: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
