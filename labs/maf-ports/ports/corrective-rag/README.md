# corrective-rag — 補正ループ RAG + Azure AI Search(Port 4)

元: [`rag_tutorials/corrective_rag`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/rag_tutorials/corrective_rag)(LangChain + LangGraph + Qdrant + Tavily + Streamlit、454 行)

## 元の構成(5行)

- Streamlit で文書 URL/アップロードを受け、tiktoken ベースで分割(500 トークン・重複 100)→ Qdrant(コサイン・1536 次元、埋め込みは OpenAI text-embedding-3-small)へ投入し `as_retriever()`(k=4)で検索
- LangGraph `StateGraph`(state は `{"keys": Dict[str, any]}` の**無型 dict 1 個**): `retrieve → grade_documents → (conditional) → generate | transform_query → web_search → generate → END`
- `grade_documents` は文書ごとに Claude へ `{"score": "yes"/"no"}` の JSON を要求し `re.search(r'\{.*\}')` + `json.loads` で緩くパース。1 件でも "no" なら `run_web_search="Yes"`(文字列フラグ)。採点エラー時は安全側に文書を残す
- `transform_query` が質問を検索最適化クエリへ書換(state の question を**上書き**)→ Tavily 検索(max 3 件・tenacity 3 試行の指数リトライ)。結果は Title/Content 連結の **1 Document** に束ねて追加。失敗・0 件時は文書を変えずに続行
- **補正パスは一方向で最大 1 回**(web_search → generate は無条件エッジ。再採点・再書換のループは存在しない — CRAG 論文のループはこの実装では単発パスに簡略化されている)

## LangGraph → MAF 対応表(本ポートの核心)

| 元(LangGraph) | 移植後(MAF core) | 備考 |
| --- | --- | --- |
| `StateGraph(GraphState)` の共有 dict `{"keys": {...}}` | **エッジごとの型付きメッセージ**: `Retrieval` / `GradeOutcome` / `RewriteOutcome` / `WebSearchOutcome` | 全ノードが読める可変 dict → そのエッジで必要な値だけ運ぶ(学び 1) |
| `add_node("retrieve", retrieve)` | `RetrieveExecutor(id="retrieve")` | retriever は `SupportsRetrieve` protocol 注入(AI Search 実接続はライブのみ) |
| `add_node("grade_documents", ...)` | `GradeExecutor(id="grade_documents")` | 文書ごと逐次採点。`response_format=GradeScore` + lenient フォールバック |
| `add_conditional_edges(grade, decide_to_generate, {...})` | `add_switch_case_edge_group(grade, [Case(needs_web_search), Default])` | `run_web_search == "Yes"`(文字列)→ `GradeOutcome.needs_web_search`(bool) |
| `add_node("transform_query", ...)`(question を上書き) | `TransformQueryExecutor` → `RewriteOutcome(question, original_question)` | 上書きという暗黙の副作用を、書換前後 2 フィールドで明示化 |
| `add_node("web_search", ...)`(Tavily + tenacity) | `WebSearchExecutor`(自前 DDG + `search_with_retry`) | 3 試行・4s/8s 待ちを移植。sleep 注入でオフラインテスト可能 |
| `add_edge("web_search", "generate")`(無条件) | `.add_edge(search, generate)` | Web 結果を再採点しない単発補正を忠実に踏襲 |
| `set_entry_point("retrieve")` / `END` | `WorkflowBuilder(start_executor=retrieve, output_from=[generate])` | |
| `app.stream(inputs)` の step 表示(Streamlit expander) | `workflow.run(q, stream=True)` の intermediate イベント | `DocsRetrieved` / `GradeDecided` / `QueryRewritten` / `WebSearched` |
| `generate` ノード(1 関数で両経路を受ける) | `GenerateExecutor` の **2 handler**(`GradeOutcome` / `WebSearchOutcome`) | 合流ノードは受信型で経路が分かる(dict ではこの区別が消えていた) |

## 移植後の構成

```
                                      ┌─[Default: 全て関連]──────────────────────────▶ generate ─▶ answer
question ─▶ retrieve ─▶ grade_documents┤  (needs_web_search == False)
        (AI Search      (文書ごとに    │
         ベクトル検索)   yes/no 採点)  └─[Case: 低関連あり]─▶ transform_query ─▶ web_search ─▶ generate ─▶ answer
                                                             (クエリ書換)        (DDG・3試行)   (書換後クエリ+
                                                                                               残存文書+Web結果)
```

## 設計判断

### Qdrant → Azure AI Search(**Free SKU**)

- `infra/main.bicep` で `sku: { name: 'free' }` の検索サービスを作成(コスト最小・月額ゼロ)。
- **Free の制約**: インデックス **3 個**まで・ストレージ **50 MB**・レプリカ/パーティション拡張不可・SLA なし・**セマンティックランカー使用不可**(1 サブスクリプションに 1 サービスまで)。本コーパス(11 チャンク)には十分。
- **本番との差**: 本番は Basic 以上+**セマンティックランカー**(意味的リランキング)+ハイブリッド検索(BM25+ベクトルの RRF 融合)が定石。本ポートは元実装に合わせた純ベクトル検索だが、`AzureSearchClientAdapter.search` の `search_text=None` に質問文を渡すだけでハイブリッドになる(学び 2)。
- インデックス定義+文書投入は **ARM/Bicep では書けない**(データプレーン API)ため `scripts/setup_index.py` に分離。

### 埋め込み: **クライアント側埋め込み(integrated vectorization なし)を採用**

- インデックスはベクトルフィールド(1536 次元・HNSW)のみ持ち、埋め込みは投入時(setup_index.py)もクエリ時(`OpenAIEmbedder`)もクライアント側で text-embedding-3-small を呼ぶ。
- 採用理由: (1) 元実装が同じ構造(LangChain `OpenAIEmbeddings` によるクライアント側埋め込み)で忠実、(2) integrated vectorization はベクトライザ+(取り込み自動化まで含めると)インデクサ/スキルセットの構成が必要で、本ポートの主題(補正ワークフローの移植)から外れる、(3) 埋め込みの呼び出し回数・コストがコードから見えて学習に向く。
- **text-embedding-3-small は共有基盤(shared.bicep)に追加せず**、本ポートの `infra/main.bicep` が共有 Foundry アカウントへデプロイを追加する(`Microsoft.CognitiveServices/accounts/deployments`・GlobalStandard capacity 10)。共有基盤を「全ポート共通の最小構成」に保つための線引き。
- トレードオフ: クエリのたびに埋め込み API を 1 回余計に呼ぶ(レイテンシ+微小コスト)。本番で integrated vectorization(`VectorizableTextQuery`)にすれば検索サービス側が埋め込みを代行し、クライアントは質問文を送るだけになる。

### 補正「ループ」はループしない(元実装に忠実)

元実装の補正パスは transform_query → web_search → generate の一方向 DAG で、再採点・再書換は存在しない。移植も同じトポロジを保ち、**書換・Web 検索は最大 1 回**(`test_single_corrective_pass_no_regrade_or_rerewrite` で固定)。無限ループ防止のカウンタは不要 — グラフ構造そのものが上限。唯一のリトライは Web 検索のトランスポートレベル 3 試行(元 tenacity → `search_with_retry`、待ち 4s/8s も一致)。

### その他

- Web 検索: Tavily(要 API キー)→ キーレス自前 DDG(`search.py` は ports/research-handoff からコピー。出典: ports/trend-analysis)。結果を 1 文書に束ねる形・失敗/0 件時に文書を変えず続行する挙動は元実装どおり
- モデル: claude-sonnet-4-5(temperature=0)→ Foundry の共有デプロイ(gpt-5.4-mini)を 3 役割(採点・書換・生成)で共用。元に system prompt がないため instructions は与えず、PromptTemplate 原文を実行メッセージとして送る
- 元実装の quirk も踏襲: 検索 0 件時は採点ループが回らず Web 検索フラグが立たないまま**空コンテキストで直接生成**される(`test_empty_retrieval_goes_direct_with_empty_context`)。補正すべきかは設計判断だが、移植では「元の挙動の記録」を優先
- Streamlit → CLI(`uv run corrective-rag-maf "question" [--json] [--top-k N]`)。文書取り込み UI は setup_index.py に置換

## 実行

```bash
uv sync --extra dev --extra live
uv run pytest                      # オフライン(ネットワーク不要・37 件)

# --- ライブ(要 共有基盤 + 本ポートの infra デプロイ + ../../.env)---
az deployment group create -g rg-maf-ports -f infra/main.bicep -p baseName=mafports
#   → 出力 searchEndpoint / searchAdminKey を ../../.env の
#     AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_ADMIN_KEY に転記

uv run python scripts/setup_index.py      # インデックス作成+data/*.md 投入(1 回)
uv run corrective-rag-maf "Azure AI Search の Free レベルにはどんな制約がありますか?"
uv run corrective-rag-maf --json "Azure AI Search の Basic レベルは月額いくら?"  # 補正パス期待
uv run pytest -m live                     # ライブスモーク(インデックス存在前提)
```

インフラ: 共有基盤(existing 参照)+固有リソース 2 つ — AI Search(Free)と text-embedding-3-small デプロイ。使わない期間はリソースグループごと削除可(インデックスは setup_index.py で再構築できるためステートレス)。

## 評価

`tests/eval_dataset.jsonl`(7 ケース)は各ケースに `expected_route`(direct / corrective)を明記。コーパス内で完結する質問(Free レベル制約、埋め込み次元数)は direct、コーパス外・鮮度依存(現行価格、今週のニュース)は corrective が期待値。直行すると幻覚価格が出る「分岐ミスの実害」ケースと、片側だけコーパスにある境界ケース(Qdrant vs AI Search)を含む。

**groundedness の測り方(次ステップ)**: 本ポートの grader は「検索結果が質問に関連するか」を実行時に測っているが、**最終回答がコンテキストに接地しているか**は別の関心事。`--json` 出力の `documents`(生成に使ったコンテキスト。Web 経由なら web_search 文書を含む)+ `answer` + 質問の 3 つ組を Foundry の **Groundedness 評価器**(azure-ai-projects evals API / azure-ai-evaluation)に渡すと、補正パスの有無で接地性がどう変わるかを比較できる。Retrieval 評価器(取得文書自体の関連性)と併用すると「リトリーバが悪いのか、grader が悪いのか、生成が悪いのか」を切り分けられる。

## 検証結果(2026-07-31)

- オフラインテスト 37 passed / ruff clean / `az bicep build` OK(生成 json は削除)
- ライブスモーク・実デプロイは未実施(呼び出し元で実施)。手順: infra デプロイ → .env 転記 → `setup_index.py` → `pytest -m live`。トレース到達の確認クエリ:

```bash
az monitor app-insights query --app appi-mafports -g rg-maf-ports \
  --analytics-query "dependencies | where timestamp > ago(30m) | summarize count() by name"
```

## 検証結果(2026-07-31 ライブ)

- インフラ: AI Search Free(srch-mafports)+ text-embedding-3-small を共有 Foundry へ追加デプロイ。`setup_index.py --recreate` で 11 チャンク投入
- in-domain 質問: retrieve 4 → grader が 3/4 棄却 → **補正パス発火**(書換+Web 検索 3 件)→ 正答(hosted agent の従量課金)。※採点が厳格で in-domain でも補正パスに入った — 「直行生成」経路はオフラインテストでのみ検証
- out-of-domain 質問: 全棄却 → 書換 → Web 検索 → 誠実な回答(未発表と回答)
- トレース: `executor.process`(retrieve/grade/transform_query/web_search/generate)+ `invoke_agent grader_agent`×6(**文書ごとの採点が個別スパン化**)を App Insights で確認
- 修正: 非同期 azure-search-documents に `aiohttp` が必要(依存へ追加)

## 学び(MAF vs 元構成)

1. **状態管理の差 — LangGraph は「全ノード共有の可変 dict」、MAF は「エッジを流れる型付きメッセージ」。**元コードの state は `{"keys": Dict[str, any]}` で、誰が question を上書きしたか(transform_query)、run_web_search がいつ立つか(grade)、generation がいつ入るか(generate)が**全部読まないと分からない**。MAF 移植では同じ情報が `RewriteOutcome(question, original_question)` のような型に落ち、暗黙の上書きが 2 フィールドの並置として顕在化した。代償は 2 つ: (a) メッセージ dataclass が 4 つ増える、(b) 合流ノード(generate)が経路ごとの handler を持つ必要がある(LangGraph は dict から取るだけなので 1 関数)。**「状態に何が入っているか」をスキーマとして固定したい業務システムでは MAF 型が向き、研究コードのように state の形を頻繁に変える探索フェーズでは LangGraph の dict が速い** — SI の技術選定ではこの開発フェーズの違いが効く。なお LangGraph も TypedDict/Pydantic で state を型付けできる(この元コードが使っていないだけ)ので、正確には「フレームワークの差」半分、「書き手の規律をフレームワークがどれだけ強制するか」の差が半分。MAF はハンドラ引数の型がルーティングに直結するため、無規律な状態共有が**構造的に書きにくい**。
2. **Qdrant → Azure AI Search 置換は「検索コードは楽、周辺の運用設計が本題」。**楽だった点: インデックス定義(HNSW+ベクトルフィールド)は SDK で 30 行、クエリは `VectorizedQuery` 1 個で、LangChain の vectorstore 抽象がなくても困らなかった。element 数 11 の学習コーパスなら Free SKU で足り、月額ゼロで本物のマネージド検索が触れる。難しかった/考えることが増えた点: (a) LangChain `Qdrant.as_retriever()` は**埋め込みの存在自体を隠す**が、素の AI Search では埋め込みモデルのデプロイ(infra)・次元数の一致(setup_index.py とクエリ側)・呼び出しコストが全部自分の設計項目になる。(b) インデックスは ARM 外(データプレーン)なので、Bicep(サービス)+スクリプト(インデックス)の**2 段デプロイ**になり、Qdrant の「コード内で create_collection」より運用の段取りが増える — 引き換えに「インフラとデータの境界」が明確になり、これは本番では利点。(c) SKU 選定が検索品質に直結する(Free はセマンティックランカー不可。本番の Basic+ハイブリッド+リランカーは、元実装の純コサイン検索より品質の上げ幅が大きい)。**「ベクトル DB の置換」は API の置換ではなく、検索品質・コスト・運用のレバーがどこにあるかの再学習**だった。
3. **「補正ループ」という名前と実装のズレが、グラフを書き直すと露呈する。**CRAG は論文的には「評価→補正を繰り返す」印象を与えるが、この元実装は再採点なしの単発 DAG で、Web 結果は無検証で生成に入る。LangGraph の dict-state だとこのズレは読み流しやすいが、MAF でエッジを 1 本ずつ張り直すと「web_search → generate が無条件」であることを設計判断として書かされる(README にも書いた)。research-handoff の学び 3(宣言と実挙動のズレの洗い出し)と同型で、**移植とは元アプリの本当の制御フローを確定させる作業**。おまけに「検索 0 件だと Web 検索に行かず空コンテキスト生成」という quirk もテストで固定できた — 元の Streamlit 実装ではまず気づけない挙動。
4. **grader の「regex で JSON を拾う」が、response_format+lenient パーサの 3 段構えに正規化できた。**元実装の `re.search(r'\{.*\}')` は素朴だが思想は正しい(LLM は JSON を散文で包む)。MAF では `ChatOptions(response_format=GradeScore)` のネイティブ構造化出力を第 1 経路にし、balanced-slice 抽出→「エラー時は文書を残す」安全側フォールバックまで全経路をオフラインテストで固定した。さらに `score: Literal["yes","no"]` にしたことで、元実装なら黙って no 扱いになる `"maybe"` が明示的にエラー経路(=文書温存)に落ちる。**実行時の自己採点(grader)とオフライン評価(Foundry の Retrieval / Groundedness 評価器)は同じ関心事の実行時/開発時の分担**であり、この対応関係を押さえると RAG の品質改善の議論が整理される(評価セクション参照)。
5. **tenacity のような「デコレータでリトライ」は、そのまま移植せず sleep 注入の関数に開くとテスト資産になる。**`@retry(stop_after_attempt(3), wait_exponential(...))` は 1 行だが、テストで実際に 4 秒待つか mock で時間を偽装するかの二択になりがち。`search_with_retry(fn, query, sleep=...)` に開けば、試行回数・待ち秒列(4s/8s)・最終失敗の伝播をネットワークなしで 3 テストに固定できた。挙動は元と同一で、依存が 1 つ減る。
