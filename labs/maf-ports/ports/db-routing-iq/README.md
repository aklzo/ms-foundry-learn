# db-routing-iq — 複数ナレッジソース振り分け + Foundry IQ agentic retrieval(Port 10)

元: [`rag_tutorials/rag_database_routing`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/rag_tutorials/rag_database_routing)(LangChain + agno + LangGraph + Qdrant + Streamlit、388 行)

## 元の構成(5行)

- Streamlit UI。PDF を 3 つの「データベース」(Product Information / Customer Support & FAQ / Financial Information)のいずれかにアップロード → 1000 文字/重複 200 でチャンク化 → Qdrant の対応コレクション(コサイン・1536 次元、OpenAI text-embedding-3-small)へ投入
- 質問は**三段カスケード**でルーティング: 段 1 = 全コレクションを類似度検索して平均スコア最大のものを採用(閾値 0.5)→ 段 2 = 閾値未満なら agno エージェントが 'products' | 'support' | 'finance' を 1 語で返す LLM ルート → 段 3 = それも失敗なら Web fallback
- 確定したコレクションに対し LangChain `create_retrieval_chain`(k=4)で回答生成(system prompt は「コンテキストに厳密・簡潔・不足は認める」)
- Web fallback は LangGraph `create_react_agent` + DuckDuckGo ツール(recursion_limit=100)。回答は `Web Search Result:` プレフィックス付きで表示、検索失敗時は素の LLM 回答に落ちる
- ルーティングの経過(similarity routing / LLM routing / fallback)は st.success / st.warning で逐次表示

## 本ポートの核心 = アプリ側の三段カスケードを「サービス側の 1 機能」に置き換える

元アプリが 150 行かけて実装したルーティング(全 DB 検索→スコア比較→LLM ルート)は、Foundry IQ(Azure AI Search の **agentic retrieval**)では knowledge base の構成プロパティになる。Port 4(corrective-rag)が AI Search に**直結**して自前 CRAG を組んだのに対し、本ポートは検索の**上のオーケストレーション層**(クエリ分解・ソース選択・並列実行・L2 リランク・統合)をサービスに委譲し、その差を実測する。

| 元(アプリ側の実装) | 移植後(Foundry IQ のサービス側機能) |
| --- | --- |
| Qdrant コレクション ×3 | 検索インデックス ×3 を **searchIndex knowledge source** ×3 で包む |
| 段 1: 全 DB を `similarity_search_with_score` → 平均スコア比較・閾値 0.5 | knowledge base が**全ソースへ副クエリを並列発行**し、セマンティックランカー(L2)が統一リランク — 「どこが一番良いか」の比較がサービス内蔵 |
| 段 2: agno ルーティングエージェント(1 語で DB 名を返す) | `retrievalReasoningEffort: low` の **LLM クエリプランニング**がソースを選択。判断材料はインデックス/KS の `description` と KB の `retrievalInstructions`(元 instructions 1〜3 をここへ移植) |
| 段 3: LangGraph ReAct + DuckDuckGo | MAF エージェントの `web_search` 関数ツール(自前 DDG。**web knowledge source を使わない判断**は下記) |
| `create_retrieval_chain` の回答生成 | MAF エージェント(gpt-5.4-mini)が MCP ツール結果から回答統合(KB の `answerSynthesis` は使わない判断は下記) |
| エージェント→検索の接続 | **MCP 経由**: KB ごとの `{search-endpoint}/knowledgebases/{kb}/mcp?api-version=...` に公開ツール `knowledge_base_retrieve`。MAF の `MCPStreamableHTTPTool` + `http_client`(api-key ヘッダー)— Port 6 のパターン流用 |
| Streamlit の PDF アップロード | `scripts/setup_kb.py`(data/*.md → インデックス+KS+KB の一括構築) |

## 実装前調査の結果(2026-07、Learn ドキュメント精読)

### SKU: Free に「枠」はあるが動作保証がなく、S3 HD は不可 → **Basic を採用**

- **agentic retrieval のサービス上限表**(search-limits-quotas-capacity): knowledge source / knowledge base の枠は **Free = 各 3 個**、Basic = 5 or 15、**S3 HD = 0(作成不可)** — survey の「S3 HD 不可」はこの表で裏が取れた
- しかし agentic retrieval は各副クエリが必ず**セマンティックランカー(L2)**を通り、セマンティックランカーのスループット上限表は **Basic 始まりで Free 列が存在しない**。KB 作成 how-to も「モデルへの RBAC(MI)を使うなら Basic 以上」と明記(Free は MI 不可 → モデル接続はキー直書きのみ)
- Free 固有の追加リスク: インデックス 3 個上限(本ポートがちょうど 3 使用で余裕ゼロ)/ 1 サブスクリプション 1 サービス(Port 4 の Free サービスを再デプロイすると衝突)
- 結論: 「オブジェクトは作れそうだが検索パスの動作保証がない」ため **Basic** を選定。**コスト注意: Basic は時間課金(約 $0.10/時、放置すると月 $75 規模)。検証後はリソースグループごと削除する前提**(KB は setup_kb.py で数分で再構築できるステートレス設計)
- 課金は 2 系統: AI Search 側は**リトリーバルトークン課金**(月次無料枠あり。従量は明示的にオプトイン)+ Azure OpenAI 側はクエリプランニングの**トークン課金**(KB に紐づけたデプロイに発生)

### knowledge base 作成 API の要点

- オブジェクトは 3 層: **knowledge source**(コンテンツ定義。searchIndex / azureBlob / web / MCP server 等 12 種)→ **knowledge base**(KS 束+モデル+検索既定)→ **retrieve アクション / MCP エンドポイント**(実行)。KS が先、KB が後(名前参照)。削除は逆順
- api-version の分水嶺: **2026-04-01(GA)は最小限の抽出検索のみ**。LLM クエリプランニング(=本ポートの核心)・answer synthesis・reasoning effort は **2026-05-01-preview** が必要。**「ルーティングの委譲」はまだプレビュー機能**である点が本番採用判断の要注意点
- インデックス側の必須要件: searchable+retrievable な文字列フィールド+**semantic configuration(prioritizedContentFields)**。ベクトルは推奨(vectorizer 必須)であって必須ではない
- KB の `models[]`(azureOpenAI・resourceUri+deploymentId+apiKey/MI)は low/medium effort のプランニングに使われる。gpt-5.4-mini は 2026-05-01-preview のサポートモデル表に含まれる

### MCP 経由接続

- KB ごとに `{search-endpoint}/knowledgebases/{kb}/mcp?api-version=2026-05-01-preview` が**単体の MCP サーバー**として立ち、公開ツールは **`knowledge_base_retrieve` の 1 つだけ**
- 認証は `Authorization: Bearer`(Search Index Data Reader ロール・推奨)か **`api-key`(管理キー・開発用)**ヘッダー。ラボはキーで統一
- MCP ツール結果は retrieve アクションの `response/activity/references` 封筒**ではなく**、`result.content[].text` に**グラウンディングデータの JSON 文字列**が入る平坦な形(activity ログは取れない — 学び 4)
- Foundry Agent Service から繋ぐ場合は project connection(`RemoteTool` カテゴリ+`ProjectManagedIdentity`)がヘッダーを注入する。本ポートは MAF クライアント実行なので Port 6 の `http_client` パターン(接続時からヘッダーが要るため `header_provider` 不可)をそのまま流用

## 移植後の構成

```
質問 ─▶ db_routing_agent(MAF Agent, gpt-5.4-mini)
          ├─ knowledge_base_retrieve(MCPStreamableHTTPTool)─▶ AI Search knowledge base
          │     └ httpx.AsyncClient(api-key ヘッダー)          ├ LLM クエリプランニング(low)
          │                                                    ├ products / support / finance KS へ副クエリ並列
          │                                                    └ L2 セマンティックリランク → グラウンディング返却
          └─ web_search(自前 DDG 関数ツール)← KB が空振りのときだけ(instructions で制御)
        ─▶ 回答(出典タイトル付き。Web 由来は "Web Search Result:" プレフィックス)
```

- ペイロード組み立ては [kb_setup.py](./src/db_routing_iq_maf/kb_setup.py)(全て純関数・18 テストで固定)、HTTP を貼るのは [scripts/setup_kb.py](./scripts/setup_kb.py) のみ
- ルーティングの観測点は「どのツールが呼ばれたか」([query.py](./src/db_routing_iq_maf/query.py) の `summarize_tool_calls`)— 元アプリの st.success("Using ... routing") に対応
- Streamlit → CLI(`db-routing-iq-maf "質問" [--json] [--timeout]`)

## 設計判断

### ルーティング三段のうち二段をサービスへ、Web fallback はエージェントに残す

段 1(閾値検索)と段 2(LLM ルート)は knowledge base の内側に消える。段 3(Web fallback)は **KB の web knowledge source を使わず自前 DDG の関数ツール**にした。理由: (1) web KS は Bing 実行=**データが Azure コンプライアンス境界の外へ**流れ、別課金(PORTING.md §2 の Web search と同じ契約論点)、(2) web KS を足すと KS 数が 4 になり、reasoning effort によっては KB あたり上限(low で 3 の版がある)に触れる、(3) 自前 DDG は Port 1/3/4 で確立済みで `MockTransport` によるオフラインテストが利く。「KB が空振りしたときだけ web_search を呼ぶ」判断は instructions ベース(元アプリでは `route_query` の None 返しというコードだった分岐が、プロンプト規約になる)。

### ベクトルなし(テキスト+L2 リランクのみ)

元は 1536 次元コサインの純ベクトル検索だが、本ポートのインデックスは**ベクトルフィールドを持たない**。agentic retrieval ではベクトルは推奨(vectorizer 必須)であって必須でなく、キーワード副クエリ+セマンティックランカーで小規模コーパスには十分。これにより埋め込みデプロイ(Port 4 の main.bicep が足したもの)も vectorizer 構成も不要になり、**「埋め込みの管理そのものが消える」**構成になる。品質を上げる場合は vectorizer 付きベクトルフィールドを足せば KB 側が自動でハイブリッド実行する(コード変更不要)。

### 回答統合はエージェント側(outputMode 既定のまま)

KB の `answerSynthesis`(サービス側で回答文まで生成)は使わず、KB は抽出的グラウンディングを返し、MAF エージェントが回答を組み立てる。元アプリの構造(retriever と回答チェーンの分離)に忠実で、回答規約(コンテキストに厳密・簡潔・出典明示・"Web Search Result:")を instructions で一元管理できる。answerSynthesis にすると LLM 呼び出しが KB 内+エージェントの二重になる。

### SDK ではなく REST(httpx)で KB を作る

knowledge base 系を扱える azure-search-documents は **preview 版(`pip install --pre`)が必要**。プレビュー SDK のピン管理より、REST ペイロード(Learn のリファレンスの JSON と 1:1)を純関数で組み立てるほうがテスト容易性と可搬性が高い(critique-loop の evals API で確立した「素の dict」方針)。依存も httpx だけで済む。

### その他

- インデックス/KS/KB は**データプレーン**のため Bicep では書けない → `infra/main.bicep`(AI Search Basic のみ)+ `scripts/setup_kb.py` の 2 段デプロイ(tech-selection-guide §2-2 の定型)
- `mcp>=1.24,<2` の上限ピン(Port 6 で実測した罠)を pyproject に明記
- 全体タイムアウト(180s)は元アプリに無い運用上の追加(Streamlit の spinner 任せだったもの)

## 実行

```bash
uv sync --extra dev
uv run pytest                      # オフライン(ネットワーク不要・54 件)

# --- ライブ(要 共有基盤 + ../../.env)---
az deployment group create -g rg-maf-ports -f infra/main.bicep -p baseName=mafportsw2
#   → 出力 searchEndpoint / searchAdminKey を ../../.env の
#     AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_ADMIN_KEY に転記

uv run python scripts/setup_kb.py             # インデックス×3+KS×3+KB 作成(1 回)
uv run db-routing-iq-maf "Aurora X10 の本体重量とバッテリーでの連続投影時間は?"   # → products
uv run db-routing-iq-maf "返品は何日以内に申請すればいいですか?"                  # → support
uv run db-routing-iq-maf --json "FY2025 の売上高と前年比は?"                      # → finance
uv run db-routing-iq-maf "2026 年現在の日本の首相は誰ですか?"                     # → web fallback

uv sync --extra dev --extra live && uv run pytest -m live   # ライブスモーク(4 問)
```

**コスト注意**: AI Search **Basic は時間課金**(検証が終わったらリソースグループごと削除する。`setup_kb.py` で再構築可能)。加えて KB のクエリプランニングは共有デプロイ(gpt-5.4-mini)への**トークン課金**、リトリーバル(リランク)は AI Search 側のトークン課金(月次無料枠内で収まる規模)。

## 評価

[tests/eval_dataset.jsonl](./tests/eval_dataset.jsonl)(7 ケース)は 3 ドメイン各 2 問+ドメイン外 1 問。各ケースに `expected_source`(products / support / finance / web)と `expected_fact`(**期待ドメインのコーパスにしか存在しない数値ファクト** — 1.2kg / 19dB / 30 日以内 / 合計 3 年 / 84 億円 / 24 円)を付し、`test_expected_fact_exists_only_in_expected_domain` がデータセット↔コーパスの整合(ファクトの一意性)をオフラインで固定する。ライブでは「正答が返れば正しいソースから引いた」と推論できるのはこの一意性のおかげ。ルーティング品質を定量evalする場合は、`--json` の `tool_calls` + 回答を Foundry の Task adherence / Groundedness 評価器に渡す(critique-loop の run_cloud_eval.py の型を流用可)。

## 検証結果(2026-07-31)

- オフラインテスト **54 passed** / ruff clean / `az bicep build` OK(生成 json は削除)
- ライブスモーク・実デプロイは未実施(呼び出し元で実施)。手順:
  1. `az deployment group create ...`(上記)→ .env 転記
  2. `uv run python scripts/setup_kb.py`(preview API のエラーはレスポンス本文をそのまま表示する — KB の `models` 受理・`retrievalReasoningEffort` の形は実サービスで初検証になる点に注意)
  3. `uv sync --extra dev --extra live` → `uv run pytest -m live`(3 ドメイン各 1 問+ドメイン外 1 問)
  4. CLI 1 回 → トレース到達の確認クエリ:
     ```bash
     az monitor app-insights query --app appi-mafportsw2 -g rg-maf-ports \
       --analytics-query "dependencies | where timestamp > ago(30m) | summarize count() by name"
     ```
     期待: `invoke_agent db_routing_agent` + `execute_tool knowledge_base_retrieve`(/ `web_search`)スパン
- 未検証の残リスク(ライブで確認すべき点): (1) 2026-05-01-preview の KB 作成ペイロード(特に `models` のキー認証と `retrievalReasoningEffort`)が本リージョンで受理されること、(2) MCP ツール結果の JSON 文字列に `domain`(sourceDataFields)が実際に含まれる形、(3) ドメイン外質問で KB が「空振り」をどう返すか(空配列か低スコア結果か)と、それを受けたエージェントが web_search に移る判断の安定性

## 検証結果(2026-07-31 ライブ)

- infra デプロイ(AI Search Basic: srch-mafportsw2-iq)→ `setup_kb.py` 一発成功(インデックス×3 → KS×3 → KB。preview API がペイロード受理 — 残リスク1解消)
- ライブスモーク **4 passed(37.3s)**: 製品(1.2kg)/サポート(30日以内)/財務(84億円)の各一意ファクトが正しいソース由来で回答され、ドメイン外質問はフォールバック動作。**アプリ側ルーティングコードゼロで三段カスケード相当が成立**
- sourceData の domain 伝搬・fallback 安定性も上記で確認(残リスク2・3解消)

## 学び(MAF/Foundry vs 元構成)

1. **アプリ側ルーティング(元実装・Port 4 の自前 CRAG)vs サービス側 agentic retrieval — コードが消えるのではなく、「制御コード」が「宣言+プロンプト」に変換される。**元アプリの三段カスケード約 150 行(スコア比較・閾値・1 語 LLM ルート・パース)は、KB では `retrievalInstructions` 1 段落+KS の `description` ×3+`retrievalReasoningEffort: low` という**宣言**に置き換わった。Port 4 の CRAG(採点→分岐→書換の自前グラフ)と比べると、得るものは (a) 副クエリ並列+統一 L2 リランクという自前では書けない品質機構、(b) 会話履歴込みのクエリ分解、(c) KB の再利用性(同じ KB を別エージェント・Copilot・Cursor からも繋げる)。失うものは (d) **分岐の可観測性と決定性** — 元アプリの「similarity 0.72 で products に決定」というログに相当するものは MCP 経由では返らず(activity は retrieve アクション限定)、ルーティングの単体テストも書けない(Port 4 は採点器を scripted fake で固定できた)。SI の選定軸としては**「ルーティング規則を監査・単体テストしたいか(アプリ側)/検索品質と再利用性を優先するか(サービス側)」**が分水嶺。なお段 3(Web fallback)だけはサービスに移せず instructions 規約として残った — カスケードの「端」は結局アプリの責務。
2. **SKU/コストの現実 — 「Free に上限枠がある」ことと「Free で動く」ことは別物で、ドキュメントの表 3 つを突き合わせて初めて分かる。**agentic retrieval の上限表は Free に KS/KB 各 3 個の枠を与えるが、パイプラインが必ず通るセマンティックランカーのスループット表には Free 列がなく、MI も Basic 以上限定。結論として実用下限は Basic(時間課金 ~$75/月)で、Port 4 が Free で済んだのと対照的に**「サービス側機能を使うほど SKU の下限が上がる」**。S3 HD は KS/KB = 0 で明示的に不可(survey 情報の裏取り完了)。もう 1 つの現実は課金の 2 系統化: AI Search 側のリトリーバルトークン+Azure OpenAI 側のプランニングトークンで、**KB を 1 回叩くたびに LLM が(エージェントの他に)もう 1 回内側で動いている**。ラボ設計としては「Basic は使い捨て・KB はスクリプトで再構築」のステートレス規約が効く。
3. **MCP 経由接続の DX — 「KB=MCP サーバー」という設計のおかげで、Foundry 固有機能なのにクライアントは完全に汎用コードで済む。**Port 6(GitHub リモート MCP)で書いた `MCPStreamableHTTPTool` + `httpx.AsyncClient(headers=...)` のパターンが、URL とヘッダー名(Bearer → api-key)を差し替えるだけでそのまま動く構成になった。ツール定義・接続ライフサイクル(`async with agent:`)・allow-list(`allowed_tools=["knowledge_base_retrieve"]`)まで全部同型で、**「Foundry IQ の学習コスト ≒ KB オブジェクトの学習コストであり、エージェント側の統合コストはほぼゼロ」**。同じ KB に Foundry Agent Service から繋ぐ場合は project connection(MI 認証をサービスが預かる)へ、コードから接続定義へ置き場所が変わるだけ(Port 6 の学び 3 と同じ「実行点と秘密の置き場所」の軸)。一方で MCP 面の割り切りも見えた: ツール結果は `content[].text` に JSON 文字列が詰まった平坦な形で、retrieve アクションが返す `activity`(どのソースに何の副クエリを投げたか)が**落ちる**。ルーティングを観測したい運用では REST の retrieve を直接叩く監視経路を別に持つべき。
4. **「GA」の看板と使いたい機能の距離を api-version で測る癖が要る。**agentic retrieval は 2026-04-01 で GA だが、GA 面は「最小限の抽出検索」のみで、本ポートの核心(LLM ソース選択)・answerSynthesis・reasoning effort は全部 2026-05-01-preview 側にある。つまり**「複数ナレッジソースの振り分けをサービスに委譲する」というアーキテクチャ判断自体がプレビュー API への依存**を意味する(SLA なし・DPA の Preview 条項)。critique-loop の evals(SDK に enum がなくサービス側解決)と同じく、Azure の新機能は「GA の器+プレビューの中身」の二層で出てくるので、提案時は機能名でなく api-version 単位で成熟度を語る必要がある。ちなみに SDK(azure-search-documents)も KB 対応は preview 版のみで、本ポートは REST+httpx を選んだ — ペイロードが Learn のリファレンスと 1:1 になり、純関数+オフラインテスト 18 件で固定できた。
5. **サービスに委譲した機能の統合テストは「コーパス設計」に化ける。**アプリ側ルーティングなら「ルーター関数に質問を入れて期待ラベルと比較」で済むが、サービス側ルーティングは KB を叩かないと動かず、正しいソースから引いたかは応答からしか推論できない。そこで各ドメインに**そのドメインのコーパスにしか存在しない数値ファクト**(1.2kg / 30 日以内 / 84 億円 …)を意図的に埋め、「ファクトの一意性」自体をオフラインテストで固定(`test_expected_fact_exists_only_in_expected_domain`)→ ライブは「正答が返れば正しく振り分けられた」と推論する構図にした。**評価データセットとコーパスを同時に設計する(片方を後付けしない)**のは、検索系サービス機能の受け入れテスト一般に使える型だと思う。
