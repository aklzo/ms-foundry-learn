"""Web search ツール(GA)の挙動確認。

maf-ports では検索を httpx 自前(DuckDuckGo 等)にしたため組み込み Web search が
未検証だった。**注意: 追加課金あり・DPA 対象外・データはコンプライアンス境界外**
(survey 04)— probe は最小限の 2〜3 リクエストに留める。

観点:
  A. ツール型名の受理("web_search" / "web_search_preview" のどちらか)
  B. output items の構成(web_search_call の中身、クエリの見え方)
  C. 引用(url_citation)の形
  D. ツール強制(tool_choice)の可否
"""

from __future__ import annotations

import sys

from foundry_probes.common import Settings, make_project_client, section, show

QUESTION = "2026 年の Microsoft Build の開催都市はどこ?出典つきで一文で。"


def main() -> int:
    settings = Settings.from_env()
    client = make_project_client(settings).get_openai_client()

    section("A. ツール型名の受理")
    accepted = None
    for tool_type in ("web_search", "web_search_preview"):
        try:
            r = client.responses.create(
                model=settings.model, tools=[{"type": tool_type}], input=QUESTION
            )
            print(f"  type='{tool_type}' -> 受理")
            accepted = (tool_type, r)
            break
        except Exception as exc:
            print(f"  type='{tool_type}' -> {type(exc).__name__}: {str(exc)[:200]}")
    if accepted is None:
        print("!! どちらの型名も受理されず。ここで終了")
        return 1
    tool_type, r = accepted

    section("B. output items の構成")
    for item in r.output:
        d = item.model_dump()
        print(f"  type={d.get('type')} keys={sorted(d.keys())}")
        if d.get("type", "").startswith("web_search"):
            show("web_search_call item", d, limit=700)
    show("output_text", r.output_text)

    section("C. 引用(annotations)の形")
    msg = next((i for i in r.output if i.type == "message"), None)
    if msg is not None:
        annotations = msg.content[0].model_dump().get("annotations")
        show("annotations", annotations, limit=900)

    section("D. tool_choice でツール強制")
    try:
        r2 = client.responses.create(
            model=settings.model,
            tools=[{"type": tool_type}],
            tool_choice={"type": tool_type},
            input="こんにちは",
        )
        used = [i.type for i in r2.output]
        print(f"  挨拶だけの入力でも検索が走るか: output types={used}")
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {str(exc)[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
