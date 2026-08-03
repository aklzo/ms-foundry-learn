# 埋め込みのエンドポイントルーティング — 挙動発見メモ(2026-08-04 実測)

環境: text-embedding-3-small v1 / gpt-5.4-mini / japaneast

## 発見(挙動)

- **survey 08 の注記は実測どおり**。埋め込みには明確な非対称性がある:
  - アカウント `https://aif-fprobes.openai.azure.com/openai/v1` → `embeddings.create` **成功**(1536 次元、model 名も正しく返る)
  - プロジェクト `https://aif-fprobes.services.ai.azure.com/api/projects/probes/openai/v1/` → `embeddings.create` **404 NotFoundError**
- 一方 responses/chat は**両エンドポイントで成功**(アカウント経由 responses も OK)。つまり非対称なのは embeddings だけ。
- text-embedding-3-small は自前デプロイ(このラボで追加)すれば 1536 次元で普通に使える。File Search 内蔵の 3-large@256 とは別。

## つまりどころ

- **1 つのクライアント(プロジェクト経由)で chat も embeddings も、と書くと embeddings だけ 404 で落ちる。** RAG を自前実装(埋め込み+chat)するとき、embeddings 呼び出しだけアカウント `openai.azure.com/openai/v1` に向けるルーティング分岐が要る。maf-ports/corrective-rag / db-routing-iq は AI Search 側の埋め込みを使ったのでこの罠を踏まなかったが、「Foundry の埋め込みモデルを直接呼ぶ」構成では踏む。
- エラーが 404 なので「モデル未デプロイ」と誤診しやすい(実際はデプロイ済みでもエンドポイント違いで 404)。切り分けにはアカウント側で叩き直す。

## SI 判断メモ

- プロジェクトエンドポイント単一で全部済ませたい設計は embeddings で破綻する。接続情報を「プロジェクト(agent/responses 用)」と「アカウント(embeddings 用)」の 2 本持つのを標準にする。共有 .env に両方出力する構成(このラボの main.bicep がそうしている)が安全。
