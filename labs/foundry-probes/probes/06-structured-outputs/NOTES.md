# Structured outputs / json_schema — 挙動発見メモ(2026-08-04 実測)

環境: gpt-5.4-mini / japaneast / プロジェクト経由 openai client
**survey 未収録機能**(§0)。この probe が一次記録。

## 発見(挙動)

- **Responses API `text.format={type:"json_schema", strict:True}` が動作**。厳密 JSON が output_text に返り、そのまま `json.loads` 可能。
- **enum 矯正が効く**: 「'JPY円' と書いて。備考フィールドも足して」と指示しても currency は `JPY` に、余計なキーは付かない(schema が勝つ)。プロンプトインジェクションで構造を壊す攻撃に対する防御として使える。
- **Chat Completions API の `response_format={type:"json_schema", json_schema:{...}}` も動作**。Responses / Chat どちらの面でも使える。
- **`additionalProperties` を省略した strict スキーマでも 400 にならず動作した**。OpenAI 本家の strict モードは「全 object に `additionalProperties:false` と全プロパティ required」を要求するが、Foundry(gpt-5.4-mini)エンドポイントはそれを強制せず受理した。移植時に本家より緩いので、逆に本家へ戻すと落ちる可能性。

## つまりどころ

- survey に記載が無いので「使えるか」を事前に断言できなかった。→ 本 probe で GA モデルでの動作を確認。ただし全モデルで strict 対応とは限らない(モデル依存)ので、モデル差し替え時は再確認。
- MAF 経由(`ChatOptions(response_format=Pydantic)`)は内部でこの json_schema を組み立てているだけ。素の SDK でも同じ結果が得られる = MAF 依存ではない。

## SI 判断メモ

- 抽出・分類・ルーティング判断など「出力を機械処理する」用途は json_schema strict を既定にしてよい(パース失敗リスクが実質消える)。maf-ports/governed-agent の構造化出力パターンは MAF なしでも移植可能。
