# 実装知見と評価結果 — 詰まった点・公式ドキュメントの注意点・試行錯誤

2026-09-02(ラウンド 1: 5 本パイロット)/ 2026-09-03(ラウンド 2: **104 本・111 クエリ+ragas**、
ラウンド 3: **評価設計の是正と再測定**)実測。
リージョン japaneast、API `2025-11-01`、補完モデル gpt-5.4-mini、埋め込み text-embedding-3-small。
生ログは `logs/`(ローカル)、本書の転記値が一次記録。**正式な結果・図表・考察は
[report/cu-video-rag-report.pdf](./report/cu-video-rag-report.pdf)(実装チーム向けレポート第 2 版)が正**。
本書は詰まりどころの全記録と、ラウンド 1 パイロットの詳細(§4〜)を保持する。

## 0. 結果サマリ(ラウンド 3 = 104 本・111 クエリ+根拠なし 8 問。第 1 版の是正後)

ラウンド 2 の第 1 版レポートは、①回答値の動画間衝突(「毎月 3 日」が 10 本)②動画を問わない
ans@k ③チャンクの時間ずれ、の 3 点で数値が歪んでいた(§1-10・1-11)。是正して再測定した値:

- **書き起こし CER: カスタム 0.44% / prebuilt 1.34%**(micro、94 本)。prebuilt の差は
  password-reset で**先頭 23.6 秒の発話がセグメント被覆外で消えた**(CER 46%)1 本による
  (§1-13。ラウンド 2 の同じ動画は 1.8%)。それを除けば両者 0.5% 前後で同一エンジン
- 検索(全 111 問): **A(書き起こしのみ)hit@1 0.622 / hit@3 0.865 → C(日本語カスタム
  フィールド)0.730 / 0.937**(hit@1 差 +0.108、95% CI [+0.009, +0.207])。
  画面のみ情報(S タイプ 61 問)の **ans@3(正解動画限定)は A 0.000 / B 0.115 / C 0.672 / D 0.689**
  (A→C 差 +0.672、CI [+0.557, +0.787]。C→D は有意差なし)
- **画面の値の転記率(CU 出力の直接測定)= 67/67 件 100%**(カスタム screenTexts。prebuilt Summary は 17.9%)。
  C の ans@3 取り逃し 20 件は全て検索順位の問題(検索ミス/同一動画の別セグメントが上位)
- **チャンクの時間ずれ**: 単語再配分なし(A0)→ あり(A)で seg_hit@1 0.378 → 0.495
  (+0.117、CI [+0.045, +0.198])。hit@3 も +0.054
- セグメント分割: 正解ステップ境界の ±2 秒一致は recall 0.61 / precision 0.94(カスタム)。
  CU は正解より粗く切る(0.73 セグメント/ステップ)が、切る位置は正確
- **無音(テロップのみ)動画は A では索引にすら入らない**が C で検索可能
- ragas(0.4.3、判定 gpt-4.1-mini、U 除く 111 問): C が A を context_precision 0.48→0.73 /
  context_recall 0.41→0.80 / answer_correctness 0.41→0.59 で上回る。A の faithfulness 0.96 は
  「分かりません」回答(63/111)の見かけ。answer_relevancy(A 0.17 / C 0.33)は判定 LLM が 1 生成しか返さず
  短い事実回答にも低い値が付くため参考値。**棄権率**: 根拠なし U 8 問は両構成とも 100% 棄権(捏造なし)、
  正解あり質問への不要な棄権は A 56.8% → C 29.7%(S タイプ 95% → 48%)
- **コスト**(usage × Retail Prices 定価、§1-12): 104 本(72.5 分)を 1 回解析すると prebuilt $3.39 /
  カスタム 2 段 $3.61(**動画 1 時間あたり $2.68 / $2.85**、内訳は抽出 $1.26・コンテキスト化 $1.22・モデル $0.9〜1.1)。
  検証全体は約 **$12**(対応前 $8.8 = CU $7.01 + ragas 等、対応後 $3.2 = 再解析 26 本 $1.84 + ragas 等)。
  AI Search Basic の稼働は計 3.8 時間($0.5)。実課金 API(Cost Management)は当日分が未反映で未取得。
  詳細はレポート §10.2 / `logs/usage_cost.json` / [report/cost_rounds.json](./report/cost_rounds.json)

## 1. 実装で詰まった点(実際に踏んだ順)## 1. 実装で詰まった点(実際に踏んだ順)

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

### 1-7. defaults は「リソースの状態」— 再デプロイしたら再登録が必須

RG を作り直した 2 回目の検証で、defaults 登録をエイリアスなしの旧手順で流してしまい
**99 本の解析が全滅**した(エラーは 1-1 と同じ)。defaults / カスタムアナライザーは
Bicep(コントロールプレーン)に乗らない **データプレーンの状態** なので、環境再作成の
たびにセットアップスクリプトで再登録する。本ラボでは `setup_azure.sh` →
`run_pipeline.py defaults` にエイリアス登録込みで固定化した。

### 1-8. ソフト削除 → パージ → 同名再作成で CU の内部モデル解決が壊れる

RG 削除で Foundry リソースがソフト削除になり、同名で再作成するには
`az cognitiveservices account purge` が必要(そのままだと `FlagMustBeSetForRestore`)。
さらに **パージ後に同名で再作成したアカウントでは、CU の解析が
`(NotFound, 404, The Azure OpenAI deployment or resource was not found.)` で失敗し続けた**:

- 同じデプロイに対する外部からの chat/embeddings 呼び出しは 200(デプロイは正常)
- defaults の再登録・クリア・**別名デプロイへの差し替えでも解消せず**、90 分以上継続
- **別名アカウント(aif-cuvrag2)を新規作成して切り替えたら即解消**

CU 内部がアカウントの旧リソース ID を掴んだままになる模様。**検証環境を作り直すときは
同名再作成を避けて別名にするのが確実**(公式ドキュメントに記載のない実測知見)。

### 1-9. Playwright の動画録画は正解時刻の精度が出ない → スクリーンショット合成に変更

`record_video_dir` の webm は録画開始と操作開始の時刻差が測れず、音声と ±1 秒程度ずれる。
スクリーンショット+ffmpeg concat demuxer(フレームごとに表示秒数を明示)へ切り替え、
映像・音声のタイムラインを完全一致させた(CU は約 1 FPS サンプリングなので滑らかさは
不要)。concat demuxer は**最終行にファイルを再掲しないと最後の duration が無視される**。

### 1-10. セグメントの transcriptPhrases は「開始時刻のセグメント」に丸ごと付く(境界で分割されない)

ラウンド 3 のレビューで判明。`contents[]` の各セグメントが持つ `transcriptPhrases` は、
**フレーズの開始時刻が属するセグメントに丸ごと**入り、セグメント境界では分割されない。
合成ナレーションのように文間の無音が短い(0.8 秒)と 1 フレーズが 20〜30 秒に伸びるため、
例えば vpn-setup ではセグメント 0(0.9〜14.9 秒)にステップ 0〜2 の発話が入り、
セグメント 1(14.9〜25.4 秒)の書き起こしは空になる。**104 本 277 セグメント中 115 が
書き起こし空**、単語 17,219 語中 1,138 語はどのセグメントの時間範囲にも入らない(隙間)。

「セグメント=チャンク」で索引すると本文と時間範囲がずれ、seg_hit@1(正解場面が 1 位)が
過小評価される。対処は、各フレーズの `words[]`(単語タイムスタンプ)を使って
**単語をセグメントの時間範囲へ再配分**してからチャンク化する
([chunks.py](../src/cu_video_rag/chunks.py) `resplit_transcripts`。隙間の単語は最も近い
セグメントへ寄せる)。再配分なし(構成 A0)とあり(構成 A)の差はレポート §8.2 に掲載。
CER は全フレーズを開始時刻順に連結して測るため影響しない。

### 1-11. 評価データの落とし穴: 回答値の動画間衝突と「動画を問わない」ans@k

ラウンド 2 のテンプレート生成では、仕込み値を `3 + i % 5` のように採番していたため
**「毎月 3 日」が 10 本、「14 日間」「80 件」等が 2 本ずつ重複**していた(S クエリ 61 問中 16 問)。
同時に ans@k の判定が「top-k のどれかのチャンクに回答値があるか」だったため、
別の動画の同じ値でヒット扱いになる経路があった(第 1 版レポートの ans@3 0.738 は
この過大評価を含む)。是正:

- 値を動画インデックスから単調に採番して全 104 本で一意にし、**部分文字列の重なり**
  (「30 件」⊂「130 件」)も排除。`corpus.validate()` が「S クエリの回答値が他の動画の
  台本・画面に現れないこと」を機械検証する(`uv run python -m cu_video_rag.corpus`)
- ans@k を**正解動画のチャンクに限定**する定義に変更(旧定義は `ans@3_any` として参考記録)
- 定義が変わった動画は `dataset` コマンドが fingerprint 不一致で自動的に作り直し、
  古い CU 結果を削除して再解析させる(TTS はナレーションが同じなら再利用)

**教訓**: 合成データで「値の有無」を測るなら、値の一意性と判定の動画限定は最初から
機械検証に入れる。

### 1-12. コストは analyzerResults の `usage` で実測できる

各解析の応答に `usage`(`videoHours` / `contextualizationTokens` / `tokens.<model>-input|output`)が
返る([pricing-explainer](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/pricing-explainer)
の「Test with representative files」)。これを保存しておけば、単価(Retail Prices API)を掛けるだけで
動画 1 時間あたりの解析コストが出る。失敗した解析(defaults 未登録・429)は課金対象外(公式)。
本ラボでは `offline-metrics` が `logs/usage_cost.json` に集計する([cost.py](../src/cu_video_rag/cost.py))。

### 1-13. セグメントが動画の先頭・末尾を覆わないと、その区間の発話が出力から消える(実行ごとに変わる)

ラウンド 3 の再解析で、`prebuilt-videoSearch` が password-reset(62 秒)を **23.6 秒から始まる
1 セグメントだけ**で返し、先頭 23.6 秒の発話(2 ステップ分)が `transcriptPhrases` にも
`markdown`(WEBVTT)にも一切含まれなかった(CER 46%)。同じ動画・同じ音声をカスタム 2 段
アナライザーで解析した結果は 3 セグメントで先頭から覆い、CER 1.8%。ラウンド 2 の prebuilt
解析でも 1.8% だったので、**セグメント分割の揺れ(非決定性)で発話が丸ごと落ちる**ことがある。
末尾側でも同様の欠落(g67-portal-cancel: 最終セグメントが発話終端より 6 秒早く終わり、
最後の文 25 文字が欠落。ラウンド 2・3 とも再現)を観測した。

対処: 取り込み時に **セグメントの時間軸被覆を検査**する(先頭セグメントの開始 ≒ 0、
最終セグメントの終了 ≒ 動画長、大きな隙間なし)。被覆が低い動画は再解析するか、
書き起こしだけ `prebuilt-audio` / `prebuilt-video`(セグメント分割なし)で取り直して補う。
本ラボでは `offline-metrics` が `logs/segmentation.json` に被覆率(coverage)と
「発話区間の 3 秒超がどのセグメントにも入らないステップ」を記録する。
なお CER をアナライザー別に測っていたおかげで検出できた(片方だけなら「そういう精度」と
誤読していた)。**同一音声を 2 系統で書き起こして CER 差を見る**のは安価な健全性検査になる。

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

## 4. 書き起こし精度(CER)— ラウンド 1 パイロット(5 本)

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

## 5. 検索精度(ハイブリッド検索、クエリ 20 問)— ラウンド 1 パイロット

> ラウンド 2(104 本・111 クエリ)の正式結果はレポート参照。規模が小さいこのラウンドでは
> hit@k が飽和しており、以下は ans@k の設計意図と試行錯誤の記録として読むこと。

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

## 6. 処理時間・コストの実測 — ラウンド 1 パイロット

> ラウンド 3 の全量コスト実測(usage ベース、動画 1 時間あたり $2.7〜2.9)は §0 とレポート §10.2 を参照。

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
- https://docs.ragas.io (RAG 評価ライブラリ ragas。使用版 0.4.3)
- https://azure.microsoft.com/pricing/details/content-understanding/
- (プレビュー期のカスタム動画アナライザー例。GA との差分確認に使用)
  https://github.com/Azure-Samples/azure-ai-content-understanding-python/blob/main/analyzer_templates/marketing_video_segmenation_custom.json
