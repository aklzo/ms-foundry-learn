# 実装知見と評価結果 — 詰まった点・公式ドキュメントの注意点・試行錯誤

2026-09-02 実測(リージョン japaneast、API `2025-11-01`、補完モデル gpt-5.4-mini、
埋め込み text-embedding-3-small)。生ログは `logs/`(ローカル)、本書の転記値が一次記録。

## 0. 結果サマリ

- **書き起こし CER 1.13%**(日本語ナレーション 5 本、正規化後 1,418 文字)。実質的な
  誤認識は同音のドメイン語 5 箇所のみで、残りは表記ゆれ(§4)
- **動画ヒット(hit@3)は全構成で 1.000**。ただし「取得チャンクに回答の値が含まれるか
  (ans@k)」で見ると、書き起こしのみ・prebuilt そのままは **0.000〜0.167** で、
  **カスタムフィールド(日本語要約+画面内テキスト転記)を足すと ans@3 = 1.000** (§5)
- prebuilt-videoSearch のセグメント記述は**英語**で返り、画面上の値(アドレス・エラー番号
  等)を含まない。日本語 RAG では**カスタムフィールドが実質必須**というのが本検証の結論

## 1. 実装で詰まった点(実際に踏んだ順)

### 1-1. defaults のモデル登録は「モデル名」では足りない(エイリアス解決)

[クイックスタート](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/quickstart/use-rest-api)
どおり `PATCH /contentunderstanding/defaults` に
`{"modelDeployments": {"gpt-5.4-mini": "gpt-5.4-mini", ...}}`(モデル名→デプロイ名)を
登録したところ、**PATCH は成功するのに analyze が非同期で `Failed`** になった:

> This analyzer needs a 'completion' model deployment for current request, but none was
> resolved. (analyzerResults の error.innererror)

`GET /contentunderstanding/analyzers/prebuilt-videoSearch` で定義を見ると、
`models.completion` は **`prebuilt-analyzer-completion-mini` というエイリアス**を参照している
(`supportedModels.completion` に gpt-4o〜gpt-5.5 の許容リストあり)。defaults には
このエイリアス名をキーに登録する必要がある:

```json
{"modelDeployments": {
  "prebuilt-analyzer-completion-mini": "gpt-5.4-mini",
  "prebuilt-analyzer-embedding": "text-embedding-3-small"
}}
```

**教訓**: ①エラーは analyze 実行時まで遅延する(PATCH 時に検証されない)。
②prebuilt アナライザーを使う前に定義を GET して `models` キーを確認する。

### 1-2. カスタムアナライザー作成の 400 連発(スキーマ制約)

`prebuilt-videoSearch` にフィールドを足すつもりで PUT したら、順に:

| エラー | 意味 | 対処 |
|---|---|---|
| `InvalidBaseAnalyzerId: Unsupported 'baseAnalyzerId' value: 'prebuilt-videoSearch'` | base にできるのは基底アナライザーのみ([analyzer-reference](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/concepts/analyzer-reference): `prebuilt-document/audio/video/image` の 4 つ) | `prebuilt-video` を base にする |
| `'omitContent' set to true but has fields defined` | omitContent とフィールド定義は併用不可 | `omitContent: false` |
| `'segmentationDefinition' must be provided when 'enableSegment' is set to true` | `contentCategories` を外して `enableSegment` だけ残すと出る(文字列で与えても解消しなかった) | GA ドキュメントどおり `contentCategories` で分割を定義する(§1-4) |

### 1-3. アナライザーは実質イミュータブル(PUT 上書きは黙って無視)

既存 ID へ変更後の定義を PUT すると **エラーなく成功応答が返るのに変更が反映されない**
(`models` を追加しても GET で空のまま)。**DELETE(204)→ 再 PUT** で反映された。
検証中にフィールド定義を回すときはこの手順を機械化しておくこと。

### 1-4. 親の fieldSchema はセグメントに適用されない(2 段構成が必要)

`enableSegment + contentCategories` と fieldSchema を同居させたら、**カスタムフィールドが
結果のどこにも出ない**(セグメントの fields はカテゴリ委譲先 `prebuilt-videoSynopsis` が
生成する `Summary` のみ)。[analyzer-reference](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/concepts/analyzer-reference)
の contentCategories 節に答えがあった:

> The models specified in the parent analyzer's `models` property are used only for
> segmentation and classification. Each subanalyzer uses its own model configuration
> for extraction.

つまり**セグメント単位のカスタムフィールドは「フィールドを持つサブアナライザー」を
作り、親の `contentCategories.<cat>.analyzerId` から参照する 2 段構成**にする:

```
videoSearchJa(親)                     segmentFieldsJa(サブ)
  baseAnalyzerId: prebuilt-video        baseAnalyzerId: prebuilt-video
  enableSegment: true                   fieldSchema: summaryJa /
  contentCategories.segment:              screenTexts / uiActions
    description: <分割プロンプト>        models.completion: gpt-5.4-mini
    analyzerId: segmentFieldsJa
  models.completion: gpt-5.4-mini(分割用)
```

なお動画の contentCategories は **1 カテゴリのみ**サポート(同ページ)。
定義の正本: [analyzer_videosearch_ja.json](../src/cu_video_rag/analyzer_videosearch_ja.json) /
[analyzer_segment_fields_ja.json](../src/cu_video_rag/analyzer_segment_fields_ja.json)。

### 1-5. カスタムアナライザーは `models.completion` の明示が必須

prebuilt はエイリアスを内蔵しているが、カスタム定義で `models` を省くと 1-1 と同じ
「completion 未解決」で analyze が失敗する。`"models": {"completion": "gpt-5.4-mini"}`
(モデル名。デプロイ名ではない)を書く。

### 1-6. モデルデプロイの 429 がアナライザーのエラーとして返る

prebuilt とカスタムの解析を並行で走らせたら
`ResourceError ... (RateLimit, 429, Rate limit exceeded)` で analyze が Failed。
CU 自体ではなく**紐づけた補完デプロイの TPM 不足**(50K → 200K に増強して解消)。
動画解析はセグメントごとに視覚+生成を回すためトークン消費が大きい。
本番のバッチ取り込みでは専用デプロイ+クォータ設計をすること。

### 1-7. Playwright の動画録画は正解時刻の精度が出ない → スクリーンショット合成に変更

`record_video_dir` の webm は録画開始と操作開始の時刻差が測れず、音声と ±1 秒程度ずれる。
スクリーンショット+ffmpeg concat demuxer(フレームごとに表示秒数を明示)へ切り替え、
映像・音声のタイムラインを完全一致させた(CU は約 1 FPS サンプリングなので滑らかさは
不要)。concat demuxer は**最終行にファイルを再掲しないと最後の duration が無視される**。

## 2. 公式ドキュメントを見て注意して実装した点

| 注意点 | 出典 | 実装での対応 |
|---|---|---|
| GA API は `2025-11-01`。defaults PATCH も GA 版で動作(クイックスタートはプレビュー版表記) | [whats-new](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/whats-new) / [quickstart](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/quickstart/use-rest-api) | 全呼び出し `api-version=2025-11-01` で実測(プレビュー API 不使用) |
| GA でマネージドモデル容量が廃止 → 自前デプロイの紐づけが必須 | [whats-new](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/whats-new) | Bicep で 2 モデルをデプロイし defaults へ登録 |
| フレームは約 1 FPS サンプリング・512×512 に縮小(小さい文字は落ちる) | [video/overview](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/video/overview) | 画面の重要情報は 25〜40px で表示(それでも拾えるかを S タイプで測定 → 今回の文字サイズでは全件読めた) |
| 音声書き起こしは fast-transcription 対応ロケール(ja-JP 対応)・japaneast 対応 | [language-region-support](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/language-region-support) | 全リソースを japaneast に配置 |
| 入力は URL 方式+ `Operation-Location` ポーリング | [quickstart](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/quickstart/use-rest-api) | Blob + 読み取り SAS(48h)で受け渡し |
| フィールドの `description` はミニプロンプトとして扱われる(具体性が精度に直結) | [analyzer-reference](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/concepts/analyzer-reference) | screenTexts の description に「一字一句そのまま」「アドレス・エラー番号・金額・型番」等の具体例を列挙(§3) |

## 3. カスタムフィールドの設計判断(構成 C/D)

prebuilt-videoSearch の素の出力(構成 B)を見て決めた。B の問題は 2 つ:
**①セグメント記述(Summary)が英語**(日本語クエリと BM25 で噛み合わずランキングを
むしろ悪化させた — §5 の N タイプ 1.000→0.800)、**②画面上の値が記述に入らない**
(「アドレスが強調表示されている」とは書くが値そのものを書かない)。

そこで 3 フィールドを設計(サブアナライザー `segmentFieldsJa`):

| フィールド | 型 | ねらい / description の工夫 |
|---|---|---|
| `summaryJa` | string | 日本語の要約 2〜3 文。**ナレーションと画面操作の両方を含めることを明示**(英語 Summary の置き換え) |
| `screenTexts` | array\<string\> | **「一字一句そのまま書き出す」+対象の具体例(サーバーアドレス・エラー番号・設定値・要件・金額・型番・ボタン名)を列挙**。画面のみ情報の検索可能化が目的 |
| `uiActions` | array\<string\> | 操作手順の日本語列挙。「〜するには」系クエリとの語彙一致を作る |

結果、`screenTexts` は `vpn.contoso-jp.example`・`エラー 809`・`12文字以上`・
`PR-8600 Series`・`50,000円`・`2 Mbps` の**仕込んだ画面のみ情報 6 件をすべて転記できた**
(720p 画面の 25〜40px 文字。1 FPS・512×512 でも読めた)。

構成 D はさらに `screenTexts` を**独立の検索フィールド**に分け、スコアリング
プロファイル(TextWeights: content 1.0 / screen_texts 2.0)で重み付けした
([AI Search のスコアリングプロファイル](https://learn.microsoft.com/en-us/azure/search/index-add-scoring-profiles))。

## 4. 書き起こし精度(CER)

正解 = 台本(合成データのため完全一致基準)。NFKC 正規化+空白・句読点除去後
(計 1,418 文字)の文字編集距離。エンジンはアナライザーによらず同一
(prebuilt / custom で同値)。

| video | CER | 編集数/文字数 |
|---|---|---|
| vpn-setup | 0.60% | 2/336 |
| meeting-share | 0.68% | 2/294 |
| printer-duplex | 1.12% | 3/269 |
| expense-apply | 1.63% | 4/246 |
| password-reset | 1.83% | 5/273 |
| **全体(micro)** | **1.13%** | 16/1,418 |

誤りの内訳(全 12 箇所・16 文字編集を目視で全件分類):

- **表記ゆれ(意味は正しい)7 箇所**: とき→時 / 二→2 / 一→1 / うえ→上 /
  繋→つな / プリンタ→プリンター(2 箇所)
- **実質的な誤認識 5 箇所**: 社給→社級(2 箇所)/ 上長→冗長 / 長辺とじ→長辺閉じ /
  **有線→優先**(「有線接続への切り替え」が「優先接続」に)— いずれも同音のドメイン語。
  **実運用ではカスタム語彙(発音辞書)や後段の用語正規化を検討する典型パターン**

※合成音声(単一話者・雑音なし)での値であり、**実収録の研修動画に対する上限性能**と
読むこと。

## 5. 検索精度(ハイブリッド検索、クエリ 20 問)

指標: 正解動画ヒット(hit@1/@3・MRR)/ 1 位チャンクが正解ステップ時刻と重なるか
(seg_hit@1)/ 取得チャンク本文に回答の値が含まれるか(ans@k、S タイプ 6 問のみ)。

| 構成 | 対象 | n | hit@1 | hit@3 | MRR | seg_hit@1 | ans@1 | ans@3 |
|---|---|---|---|---|---|---|---|---|
| A: 書き起こしのみ | 全体 | 20 | 1.000 | 1.000 | 1.000 | 0.500 | - | - |
| | タイプ S | 6 | 1.000 | 1.000 | 1.000 | 0.667 | **0.000** | **0.000** |
| B: prebuilt-videoSearch | 全体 | 20 | 0.900 | 1.000 | 0.942 | 0.450 | - | - |
| | タイプ N | 10 | **0.800** | 1.000 | 0.883 | 0.400 | - | - |
| | タイプ S | 6 | 1.000 | 1.000 | 1.000 | 0.667 | 0.000 | 0.167 |
| C: +日本語カスタムフィールド | 全体 | 20 | 1.000 | 1.000 | 1.000 | **0.700** | - | - |
| | タイプ S | 6 | 1.000 | 1.000 | 1.000 | 0.833 | 0.667 | **1.000** |
| D: C + screenTexts 分離・重み付け | 全体 | 20 | 0.950 | 1.000 | 0.975 | 0.650 | - | - |
| | タイプ S | 6 | 1.000 | 1.000 | 1.000 | 0.833 | **0.833** | 1.000 |
| | タイプ C | 4 | **0.750** | 1.000 | 0.875 | 0.500 | - | - |

(全行は `logs/eval_*.json`。タイプ N=ナレーション由来 10 問 / S=画面のみ 6 問 /
C=紛らわしい 4 問)

### 試行錯誤の読み方(A→B→C→D で起きたこと)

1. **A(書き起こしのみ)**: 動画レベルは全問正解 — 5 本という規模では「どの動画か」は
   語彙だけで当たる。しかし **ans@k = 0.000**: 画面にしかない値は原理的に取れず、
   RAG は「画面のアドレスを入力してください」としか答えられない
2. **B(prebuilt そのまま)**: 英語 Summary がノイズになり N タイプの hit@1 が
   1.000→0.800 に**悪化**。ans@3 も 0.167(6 問中 1 問、生成が偶然値を含んだもの)。
   **日本語コンテンツに prebuilt-videoSearch を素で使うのは推奨できない**
3. **C(日本語カスタムフィールド)**: ランキング悪化が解消し、**ans@3 = 1.000**。
   ans@1 の取りこぼし 2 問は「正解動画内の別セグメントが 1 位」(回答セグメントは
   2〜3 位)という動画内順位の問題
4. **D(screenTexts 重み付け)**: ans@1 が 0.667→0.833 に改善した一方、画面語彙の
   重みが**動画間の切り分けを 1 問壊した**(C04: 「社員番号」が両動画の画面に出るため)。
   **フィールド重み付けは動画内順位と動画間判別のトレードオフ**として効く

**採用推奨は C**: top-3 チャンクを LLM に渡す一般的な RAG では ans@3 = 1.000 が効き、
ランキングの副作用がない。top-1 しか使えない制約があるときのみ D を検討。

## 6. 処理時間・コストの実測

- 解析時間(動画 58〜73 秒/本): prebuilt 43〜134 秒/本、カスタム(2 段)42〜53 秒/本。
  **概ね動画実時間の 0.7〜2 倍**で、ナレッジのバッチ取り込みには十分実用的
- セグメント数: prebuilt 計 15 / カスタム 計 17(5 本、約 5.3 分)。チャンク数 =
  インデックス A 12 / B 15 / C·D 17
- 本検証で処理した動画は再試行込みで計約 16 分。課金は「動画の分数課金+紐づけモデルの
  トークン課金」の 2 階建て([pricing explainer](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/pricing-explainer))。
  単価は変わるため見積もり時に[料金ページ](https://azure.microsoft.com/pricing/details/content-understanding/)で最新を確認すること
- 429(§1-6)のとおり、コストよりも**補完デプロイの TPM クォータ**が先に律速になる

## 7. 考察と限界

- **合成データの限界**: 画面が実録画より鮮明(非圧縮スクリーンショット由来)、話者 1 名・
  雑音なし。CER・screenTexts の転記率は上限性能。実案件では実動画でのパイロット測定を
  必ず挟むこと(本ラボのパイプラインはそのまま流用可能)
- **規模の限界**: 5 本では動画レベル検索が飽和する。数百本規模では hit@k が下がる余地が
  あり、ans@k と seg_hit の相対比較(A<B<C)が本検証の主たる持ち帰り
- **helpdesk 案件への含意**: 「画面操作研修動画の取り込み」要件には
  CU(カスタム 2 段アナライザー)→ セグメント単位チャンク → 既存 AI Search
  インデックスへの追加、が最小構成。書き起こしを別実装(Speech batch 等)する必要は
  ない(CER 1.13%)。ただし日本語では**カスタムフィールド前提**で工数を見ること

## 8. 参照した Web ページ(本書での引用)

- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/quickstart/use-rest-api
- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/whats-new
- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/video/overview
- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/language-region-support
- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/concepts/analyzer-reference
- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/pricing-explainer
- https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview
- https://learn.microsoft.com/en-us/azure/search/index-add-scoring-profiles
- https://azure.microsoft.com/pricing/details/content-understanding/
- (プレビュー期のカスタム動画アナライザー例。GA との差分確認に使用)
  https://github.com/Azure-Samples/azure-ai-content-understanding-python/blob/main/analyzer_templates/marketing_video_segmenation_custom.json
