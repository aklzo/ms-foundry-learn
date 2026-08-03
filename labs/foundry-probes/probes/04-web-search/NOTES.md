# Web search ツール — 挙動発見メモ(2026-08-04 実測)

環境: gpt-5.4-mini / japaneast / プロジェクト経由 openai client

**課金・コンプライアンス注意(survey 04)**: 内部は Grounding with Bing (Custom) Search。
**追加課金・DPA 対象外・データはコンプライアンス境界外へ送信**。probe は 4 リクエストのみ実行。

## 発見(挙動)

- ツール型名は **`web_search` が受理**される(`web_search_preview` は試行前に受理されたため未確認のまま終了 — 現行 GA 名は `web_search` で良い)。
- 追加リソース・接続(旧 Bing グラウンディング接続)不要。ツール指定だけで動く。
- `web_search_call` item の `action` に **実際の検索クエリが複数入る**(`queries` 配列)。モデルが独自にクエリを 2 本組み立てていた。監査ログ的にはここが「外に出た文字列」の実体。
- 引用は message の `annotations` に `url_citation {url, title, start_index, end_index}`。output_text 内にも markdown リンクが埋まる。
- **`tool_choice={"type": "web_search"}` で強制可能**。挨拶だけの入力でも検索が走った(=不要な外部送信・課金を強制するリスクもある。既定は auto に留めるのが無難)。

## つまりどころ

- 規制業種では「`action.queries` に入る文字列(ユーザー入力由来)が Bing 側に出る」ことを DPA 対象外と併せて説明できる必要がある。プロンプトで検索クエリに載せてよい情報を制約する設計が要る。
- 課金はツール呼び出し単位の別課金(モデルトークンとは別)。tool_choice 強制やエージェントの検索多用で膨らみやすい。

## SI 判断メモ

- maf-ports では DuckDuckGo/httpx 自前で代替したが、本番で「出典つき最新情報」が要件なら web_search が最短。ただし上記コンプライアンス制約で NG になる案件(金融・公共)が現実に多く、その場合は自前検索 API(実装例: maf-ports/trend-analysis の httpx ツール)に倒す。判断根拠として action.queries の実物をこの probe ログで示せる。
