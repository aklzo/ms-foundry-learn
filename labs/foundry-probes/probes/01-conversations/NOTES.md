# Conversations API — 挙動発見メモ(2026-08-04 実測)

環境: gpt-5.4-mini v2026-03-17 / model-router v2025-11-18 / japaneast / openai 2.53.0 + azure-ai-projects 2.4.0

## 発見(挙動)

- **サーフェスはプロジェクト経由のみ。** アカウント直下の `https://<res>.openai.azure.com/openai/v1` では `conversations.create` が 404。`AIProjectClient.get_openai_client()`(= `{project_endpoint}/openai/v1` 相当)なら成功。survey 03 の「2クライアント構成」の実態はこれ。
- **多ターン継続は期待どおり。** `responses.create(conversation=<id>)` で履歴を再送せずに状態が引き継がれる(turn2 で「青」を即答)。応答オブジェクトに `conversation.id` が返る。
- **conversation オブジェクトに TTL/expiry フィールドは無い**(`id` / `created_at` / `metadata` / `object` のみ)。明示削除するまで残る前提で設計する必要がある。保持期間の公式記載も survey に無し(§0)。
- **items は message 単位で新しい順に返る。** item には OpenAI 互換フィールドに加えて Azure 拡張 `created_by.response_id`(どの response が生成したか)と `partition_key` が付く。`phase` フィールドもある(null)。
- **`previous_response_id` 連鎖も併用可**(conversation なしのステートレス連鎖)。用途は「会話コンテナ不要の一時連鎖」。両方式は排他ではない。
- **store=False は conversation 指定と同時でも受理され、そのターンは会話に記録されない**(items 0 件)。エラーにも警告にもならないので、「conversation を渡したのに履歴が増えない」事故の温床。センシティブなターンだけ除外する用途には使える。
- **同一 conversation を別モデル(model-router)で継続できる。** 会話状態はモデル非依存。
- **model-router は非 OpenAI モデルにルーティングする**(この probe では `grok-4-1-fast-reasoning` が返った)。詳細は probes/05。

## つまりどころ

- 存在しない conversation id は **400 `Malformed identifier`**(404 ではない)。id 形式が不正なだけでも同じエラーなので、存在確認には `conversations.retrieve`(404)を使う。
- 削除後のアクセスは 404。エラーメッセージのリソース表記は `aif-fprobes@probes@AML` という内部形式で、プロジェクト名がここに出る。
- items の一覧は既定で新しい順(最新の assistant 応答が先頭)。時系列で処理するなら `order` 指定か反転が必要。
- (survey 03 より)legacy Agent Applications 経由のエージェントは conversations にアクセス不可+会話 ID 漏洩でユーザー間分離が効かない既知問題が修正中。conversation id は秘匿情報として扱うこと。

## SI 判断メモ

- maf-ports の全ポートで会話状態をクライアント側(MAF)に持ったが、「状態をサービス側に寄せて薄いクライアントにする」構成が Conversations で素直に組める。マルチデバイス継続・監査(items が正)・薄い UI の要件なら Conversations 優位。
- 逆に、会話の TTL 管理・ユーザー分離(conversation id の認可)はアプリ責務。この 2 点を軽視すると事故る。
