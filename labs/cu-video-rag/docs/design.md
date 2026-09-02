# 検証設計 — 合成データセット・パイプライン・評価

2026-09-02 時点。データセット調査の経緯は [dataset-research.md](./dataset-research.md)。

## 1. 合成データセット(日本語研修動画 5 本)

社内 IT 操作研修を模した 5 本(各 60〜75 秒、計約 5.3 分)。定義の正本は
[`src/cu_video_rag/scenarios.py`](../src/cu_video_rag/scenarios.py)(台本・画面操作・評価クエリを 1 ファイルに集約)。

| video_id | 題材 | ねらい |
|---|---|---|
| vpn-setup | 社外から VPN 接続 | 画面のみ情報 2 つ(接続先アドレス・エラー番号)。5 と語彙が被る |
| password-reset | パスワード再設定 | 画面のみ情報(パスワード要件)をダイアログ大文字で表示 |
| printer-duplex | プリンタ追加と両面印刷 | 画面のみ情報(ドライバー型番)。英数字 OCR の確認 |
| expense-apply | 経費精算の申請 | ドメイン外れのノイズ動画。画面のみ情報(上限金額) |
| meeting-share | Web 会議の画面共有 | 「接続・切断」語彙を vpn-setup と共有(紛らわしさの統制) |

### 生成方式(Playwright スクリーンショット + ffmpeg concat)

1. 日本語モック UI(1280×720、本文 26px 以上)を HTML 生成([pagegen.py](../src/cu_video_rag/pagegen.py))
2. ステップごとの台本を Azure Speech TTS(`ja-JP-NanamiNeural`)で合成し、実測秒数から表示秒数を決定
3. Playwright で操作(op)を 1 つずつ適用しスクリーンショット、ffmpeg concat demuxer で
   **フレームごとの表示秒数を明示指定**して mp4 化([record.py](../src/cu_video_rag/record.py))

Playwright の動画録画(webm)を使わない理由: 録画開始と操作開始の時刻差が測れず音声と
±1 秒程度ずれる。スクリーンショット方式は映像・音声のタイムラインが完全に一致し、
**ステップ境界の正解時刻が決定的**になる(CU は約 1 FPS サンプリングなので滑らかさは不要)。

### 評価用の仕掛け(データ設計の要点)

- **画面のみ情報(screen_only_facts)**: ナレーションでは「画面の表示を確認してください」と
  だけ言い、値そのもの(例: `vpn.contoso-jp.example`、`12文字以上・記号1つ以上`)は画面にだけ出す。
  書き起こしのみのインデックスでは**原理的に検索不能** → 視覚理解の寄与を分離測定
- **語彙の衝突**: vpn-setup と meeting-share が「接続/切断/タイムアウト」を共有し、
  検索が表層語だけで当たらないようにする
- **文字サイズ**: CU はフレームを 512×512 に縮小するため小さい文字が落ちる
  ([video/overview](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/video/overview) の制約)。
  画面のみ情報はダイアログ見出し(40px)・注記ボックス(25px)で大きく表示。
  720p→512 で約 2.5 分の 1 になっても読める想定(それでも落ちるかが検証項目)

### 評価クエリ 20 問

| タイプ | n | 内容 |
|---|---|---|
| N(ナレーション由来) | 10 | 書き起こしだけで当たるはずの質問(各動画 2 問) |
| S(画面のみ) | 6 | 正解の根拠が画面表示にしかない質問 |
| C(紛らわしい) | 4 | vpn-setup と meeting-share の切り分けが必要な質問 |

正解ラベル = (video_id, expected_step)。ステップの実時刻範囲は生成時の
`data/ground_truth/*.json` から解決する。

## 2. パイプライン

```
mp4 → Blob(SAS URL)→ CU prebuilt-videoSearch(GA 2025-11-01)→ analyzerResults JSON
    → セグメント分解(chunks.py)→ AI Search(ja.lucene + text-embedding-3-small/HNSW)
    → ハイブリッド検索(RRF 統合)→ 評価(evaluate.py)
```

- チャンク単位 = **CU が返すセグメント**(時間範囲つき)。RAG 向け出力の推奨単位
  ([video/overview](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/video/overview) の RAG 節)
- 埋め込みはアカウントエンドポイント経由(foundry-probes 08 実測: プロジェクト経由 404)

## 3. 比較するインデックス構成(試行錯誤の軸)

| 構成 | 本文に入れるもの | 意味 |
|---|---|---|
| A: transcript | CU の transcriptPhrases のみ | 「音声だけ書き起こせば十分では?」のベースライン(自前 STT 相当) |
| B: full | A + CU 生成フィールド(セグメント記述) | prebuilt-videoSearch の素の実力 |
| C: custom | A + カスタム fieldSchema(日本語要約・画面内テキスト・操作列挙) | B の観察(英語 Summary・値の欠落)を受けて設計 |
| D: split | C の screenTexts を独立フィールド化+スコアリングプロファイル重み 2.0 | C の ans@1 取りこぼし(動画内順位)への追加施策 |

仮説: N タイプは A でも当たる。S タイプは A でほぼ全滅し、B で CU の視覚記述が
拾えた分だけ当たる。B で不足するなら C/D でフィールド設計を工夫する。
(→ 実測は [findings.md](./findings.md) §5。C 採用が推奨、D はトレードオフあり)

カスタムフィールドは**サブアナライザー参照の 2 段構成**が必要
(親 `videoSearchJa` が分割、サブ `segmentFieldsJa` がフィールド生成。
理由と経緯は findings.md §1-4)。

## 4. 評価指標

| 指標 | 対象 | 定義 |
|---|---|---|
| CER | 書き起こし | 文字誤り率 = 編集距離/正解文字数。NFKC 正規化+空白・句読点除去後 |
| hit@1 / hit@3 | 検索 | 正解動画のチャンクが 1 位 / 3 位以内 |
| MRR | 検索 | 正解動画の最初の順位の逆数の平均 |
| seg_hit@1 | 検索 | 1 位チャンクが正解動画かつ正解ステップの時間範囲と重なる |

CER の正解は台本そのもの(合成データの強み)。句読点を除くのは STT の切り方の流儀差で
あり意味理解に影響しないため。

## 5. Azure 構成

`infra/main.bicep`: Foundry リソース(kind AIServices, japaneast)+ gpt-5.4-mini /
text-embedding-3-small デプロイ + Storage(動画置き場)+ AI Search basic。
CU の GA ではマネージドモデル容量が廃止され、**自前デプロイを
`PATCH /contentunderstanding/defaults` で紐づけるのが必須**
([whats-new](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/whats-new))。

ラボ簡略化のため TTS/CU/SAS はキー認証(顧客環境なら Entra ID+RBAC。GA で
`Cognitive Service Content Understanding Owner/Contributor/Reader` ロールが追加されている)。

## 6. 参照した Web ページ

- CU REST クイックスタート(API 形の正): https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/quickstart/use-rest-api
- CU what's new(GA 2025-11-01・BYO モデル必須化・RBAC): https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/whats-new
- CU video 概要(セグメント・fieldSchema・制約): https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/video/overview
- CU 言語・リージョン対応: https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/language-region-support
- Speech TTS REST(音声合成): https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech
- AI Search ハイブリッド検索(RRF): https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview
