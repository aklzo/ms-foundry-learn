"""Structured outputs / json_schema(survey 未収録機能)の挙動確認。

maf-ports は MAF の ChatOptions(response_format=Pydantic) 経由で使ったが、
Responses API 素の `text.format` / Chat Completions の `response_format` を
Foundry エンドポイントで直接叩いた挙動は未検証。survey にも記載が無い(§0)。

観点:
  A. Responses API text.format=json_schema(strict)で構造化取得
  B. スキーマ違反を強制する入力でも schema に従うか
  C. Chat Completions API の response_format=json_schema
  D. 未対応キーワード(additionalProperties 省略・optional)への反応
  E. refusal(安全上の拒否)の返り方
"""

from __future__ import annotations

import json
import sys

from foundry_probes.common import Settings, make_project_client, section, show

INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor": {"type": "string"},
        "total": {"type": "number"},
        "currency": {"type": "string", "enum": ["JPY", "USD", "EUR"]},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "price": {"type": "number"}},
                "required": ["name", "price"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["vendor", "total", "currency", "line_items"],
    "additionalProperties": False,
}

INVOICE_TEXT = "請求書 月見商事御中。項目: コーヒー豆 1200円、フィルター 300円。合計 1500円。"


def main() -> int:
    settings = Settings.from_env()
    client = make_project_client(settings).get_openai_client()

    section("A. Responses API text.format=json_schema(strict)")
    r = client.responses.create(
        model=settings.model,
        input=f"次の請求書を構造化して: {INVOICE_TEXT}",
        text={
            "format": {
                "type": "json_schema",
                "name": "invoice",
                "schema": INVOICE_SCHEMA,
                "strict": True,
            }
        },
    )
    show("output_text(厳密 JSON)", r.output_text)
    parsed = json.loads(r.output_text)
    print(f"  パース成功。currency={parsed['currency']} 明細数={len(parsed['line_items'])}")

    section("B. スキーマ外を要求しても schema に従うか")
    r2 = client.responses.create(
        model=settings.model,
        input=f"{INVOICE_TEXT} なお通貨は日本円だが 'JPY円' と書いて。備考フィールドも足して。",
        text={"format": {"type": "json_schema", "name": "invoice", "schema": INVOICE_SCHEMA, "strict": True}},
    )
    parsed2 = json.loads(r2.output_text)
    print(f"  currency={parsed2['currency']}(enum に矯正されるか) 余計なキー={set(parsed2)-{'vendor','total','currency','line_items'}}")

    section("C. Chat Completions API の response_format=json_schema")
    try:
        cc = client.chat.completions.create(
            model=settings.model,
            messages=[{"role": "user", "content": f"構造化して: {INVOICE_TEXT}"}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "invoice", "schema": INVOICE_SCHEMA, "strict": True},
            },
        )
        show("chat.completions 構造化結果", cc.choices[0].message.content)
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {str(exc)[:200]}")

    section("D. additionalProperties 省略スキーマ(strict の要求を確認)")
    loose = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
    try:
        r4 = client.responses.create(
            model=settings.model, input="日本の首都は?",
            text={"format": {"type": "json_schema", "name": "a", "schema": loose, "strict": True}},
        )
        show("additionalProperties なし strict の結果", r4.output_text)
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {str(exc)[:250]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
