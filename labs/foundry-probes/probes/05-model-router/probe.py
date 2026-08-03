"""Model router(GA v2025-11-18)の挙動確認。

観点:
  A. japaneast にデプロイできた事実(survey のリージョン表 5 リージョンに
     japaneast が無い → 表の更新が必要)
  B. 難易度の異なるプロンプトでどのモデルにルーティングされるか(response.model)
  C. 非 OpenAI モデルへのルーティング(プレビュー扱いの既定動作)
  D. usage / 課金単位の見え方(ルーティング先モデルの単価になるはず)
  E. reasoning 系パラメータ(temperature)の受理 — ルーティング先依存で挙動が変わるか
"""

from __future__ import annotations

import sys

from foundry_probes.common import Settings, make_project_client, section, show

PROMPTS = [
    ("易: 挨拶", "こんにちは!"),
    ("易: 単純事実", "日本の首都は?一語で。"),
    ("中: 短い作文", "秋の季語を使って俳句を一句。"),
    ("難: 多段推論", "3 桁の整数のうち、各桁の和が 15 で、桁を逆順にすると元より 396 大きくなるものをすべて挙げ、根拠を段階的に示して。"),
    ("難: コード", "Python で LRU キャッシュをスレッドセーフに実装して。ロック粒度の設計理由も。"),
]


def main() -> int:
    settings = Settings.from_env()
    client = make_project_client(settings).get_openai_client()

    section("B/C. プロンプト難易度別のルーティング先")
    for label, prompt in PROMPTS:
        try:
            r = client.responses.create(model="model-router", input=prompt)
            usage = r.usage.model_dump() if r.usage else {}
            print(f"  [{label}] -> model={r.model} out_tokens={usage.get('output_tokens')}")
        except Exception as exc:
            print(f"  [{label}] !! {type(exc).__name__}: {str(exc)[:150]}")

    section("D. usage の詳細(最後の応答)")
    r = client.responses.create(model="model-router", input="1+1 は?")
    show("model / usage", {"model": r.model, "usage": r.usage.model_dump() if r.usage else None})

    section("E. temperature の受理(ルーティング先が reasoning 系だと拒否されるか)")
    for temp in (0.2,):
        try:
            r = client.responses.create(model="model-router", input="サイコロを振った気持ちで 1〜6 の数字を1つ。", temperature=temp)
            print(f"  temperature={temp} -> OK(model={r.model})")
        except Exception as exc:
            print(f"  temperature={temp} -> {type(exc).__name__}: {str(exc)[:180]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
