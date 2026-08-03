# File Search + ベクトルストア — 挙動発見メモ(2026-08-04 実測)

環境: gpt-5.4-mini / japaneast / openai 2.53.0(プロジェクト経由 openai client)

## 発見(挙動)

- **埋め込みモデルの自前デプロイは不要。** アカウントに text-embedding-3-large のデプロイが無い状態でインデックス作成・検索とも成功。埋め込みはサービス管理(survey 04 の「text-embedding-3-large@256 固定」)で、**次元・モデルの変更手段は無い**。
- **チャンク既定値は survey 記載どおり実測一致**: `max_chunk_size_tokens: 800 / chunk_overlap_tokens: 400`(`vector_stores.files.create` の戻り値で確認)。
- ファイル id は `assistant-` プレフィックス。`purpose="assistants"` が現行でもそのまま通る(Responses 世代でも旧名称)。
- 小ファイル 2 件のインデックスは約 3.5 秒で completed。store の `status` と `file_counts.in_progress` の両方を見るポーリングで問題なし。
- **検索・引用は期待どおり**: `file_search_call` item + message の `annotations` に `file_citation {file_id, filename, index}`。複数ファイルからの出し分けも正答。
- **store の明示 TTL を設定できる**: `expires_after={"anchor": "last_active_at", "days": N}` → `expires_at` が入る。survey の「会話由来ストアは既定 7 日失効」に対し、**自作ストアの既定は無期限**(`expires_after: null`)。

## つまりどころ

- **store を削除してもファイル本体は残る**(`files.retrieve` が成功し続ける)。課金・データ残置の観点で `files.delete` を別途忘れないこと。ストレージは追加課金対象。
- 1 エージェント 1 ストア・1 会話 1 ストア制限(survey)があるので、テナント分離をストア分割で設計する場合は上限 10,000 ファイル/store とあわせて設計に効く。
- Private Link 未対応(survey 01)。閉域要件がある案件では File Search ではなく自前 AI Search(maf-ports/corrective-rag の構成)に倒す。

## SI 判断メモ

- 「とにかく RAG を早く」の PoC は File Search が最短(インフラ 0)。本番で閉域・埋め込みモデル指定・チャンク戦略調整が要件化したら AI Search 直に移行、という 2 段構えが実務的。移行先の実装例は maf-ports/corrective-rag。
