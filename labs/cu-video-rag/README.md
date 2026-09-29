# cu-video-rag — Content Understanding video × AI Search の精度検証ラボ

ナレーション付き画面操作研修動画を **Azure AI Content Understanding の
`prebuilt-videoSearch`(GA API `2025-11-01`)** で解析し、AI Search の
ハイブリッド検索に取り込んだときの精度を、**書き起こし(CER)と RAG 検索
(hit@k / MRR)の 2 段階で定量評価**する検証ラボ。

背景: helpdesk 案件で「社内ナレッジに画面操作の研修動画が含まれる場合に取り込みたい」
という要件が想定され、CU ベースの方式(書き起こしを別途実装しない)の実力を
実測で確かめる必要があった。

## 結論(実測サマリ 2026-09-03 第 2 版、104 本・111 クエリ+根拠なし 8 問)

自作合成の日本語研修動画 **104 本・計 72.5 分**(日本語オープンデータセット不在のため —
[調査](./docs/dataset-research.md)。形態 4 種: ナレーション UI 88 / 無音テロップ 10 /
スライド講義 5 / 長尺 3 章 1)+評価クエリ 111 問(+根拠なし 8 問)で実測。
**正式な結果・図表・考察は [docs/report/cu-video-rag-report.pdf](./docs/report/cu-video-rag-report.pdf)
(実装チーム向けレポート第 2 版)**。第 1 版のレビューで見つけた評価設計の不備 3 点
(回答値の動画間衝突・動画を問わない ans@k・チャンクの時間ずれ)を是正して再測定した
([findings 1-10〜1-13](./docs/findings.md))。

| 何を測ったか | 結果 |
|---|---|
| 書き起こし CER(94 本 micro) | **カスタム 0.44% / prebuilt 1.34%**(prebuilt は先頭 23.6 秒の発話が消えた 1 本を含む。除くと 0.5% 台。合成音声での上限性能) |
| 検索 hit@1 / hit@3(全 111 問) | 書き起こしのみ 0.622 / 0.865 → **カスタムフィールドで 0.730 / 0.937**(hit@1 の差 +0.108、95% CI [+0.01, +0.21]) |
| 回答値が**正解動画の**チャンクに含まれる率 ans@3(画面のみ情報 61 問) | 書き起こしのみ **0.000** / prebuilt 素 0.115 / **カスタムフィールド 0.672**(差 +0.67、CI [+0.56, +0.79]。取り逃しは検索順位の問題で、**画面の値そのものは 67 件中 67 件 = 100% 転記**されていた) |
| チャンクの時間ずれ(単語再配分なし A0 → あり A) | seg_hit@1 0.378 → 0.495(+0.117、CI [+0.05, +0.20]) |
| 無音(テロップのみ)動画の検索 | 書き起こしのみでは**索引に入らない**(0.000)→ カスタムで検索可能 |
| RAG 回答品質([ragas](https://docs.ragas.io) 0.4.3)と棄権率 | カスタム構成が context_recall 0.41 → 0.80 / answer_correctness 0.41 → 0.59 / context_precision 0.48 → 0.73 と優位。根拠なし 8 問は両構成とも 100% 棄権(捏造なし)、正解あり質問への不要な棄権は 57% → 30% に減少(A の faithfulness 0.96 は「分かりません」の見かけ。answer_relevancy は本データでは信頼性が低く参考値) |
| 解析時間 / コスト | 動画実時間の約 0.8〜0.9 倍(中央値)。**検証全体の概算コスト約 $12**(CU 解析 $8.8 = 104 本 × 2 アナライザー + 再解析 26 本、ragas 判定 $2.1、AI Search 等 $0.8。usage × 定価)。**研修動画 1 時間あたりの CU 解析は prebuilt 約 $2.7 / カスタム 2 段 約 $2.9**(gpt-5.4-mini Global)。実課金 API は当日分未反映のため未取得 |

**持ち帰り**: ①CU の日本語書き起こしは別途 STT を実装する必要がない水準。ただし
**セグメント分割が動画先頭を覆わないと発話が丸ごと消える**(実行依存)ので取り込み時に被覆検査が要る。
②prebuilt-videoSearch を**素のまま**日本語 RAG に使うと英語 Summary がノイズになり、
画面のみ情報もほぼ使えない。**日本語カスタムフィールド(日本語要約+画面内テキスト転記)が
実質必須**で、これには**サブアナライザー参照の 2 段構成**が必要。
③CU はセグメントの transcriptPhrases をフレーズ開始時刻のセグメントに丸ごと付けるため、
**単語タイムスタンプでセグメントへ再配分**してからチャンク化する。
④実装の詰まりどころ 13 件(defaults エイリアス・アナライザー非更新・同名再作成・
フレーズ割り当て・先頭欠落・重複セグメント等)は [docs/findings.md](./docs/findings.md) §1 に全記録。

## 構成

| パス | 内容 |
|---|---|
| [docs/dataset-research.md](./docs/dataset-research.md) | オープンデータセット調査(結論: 日本語要件を満たすものは無し → 自作合成) |
| [docs/design.md](./docs/design.md) | データ設計・評価設計・比較するインデックス構成(A/B/C) |
| [docs/findings.md](./docs/findings.md) | **成果物本体**: 詰まった点・公式の注意点・カスタムフィールド設計・試行錯誤・定量結果 |
| `src/cu_video_rag/` | シナリオ定義(=ground truth)/ ページ生成 / TTS / 録画合成 / CU クライアント / チャンク化 / 検索 / 評価 |
| `scripts/run_pipeline.py` | パイプライン CLI(dataset / defaults / upload / analyze / cer / index / eval) |
| `infra/main.bicep` | Foundry リソース+モデルデプロイ+Storage+AI Search(使い捨て RG) |
| `data/` | 生成された ground truth・評価クエリ(動画・音声・画面は再生成可能なので git 外) |

## 実行手順

詳細な実行手順と確認観点は [docs/runbook.md](./docs/runbook.md)(人間用 HTML: `docs/runbook.html`)。

```bash
# 0) 依存(初回のみ。playwright の版を上げたときもブラウザの再取得が要る)
uv sync --extra dev && uv run playwright install chromium

# 1) 基盤(課金発生。検証後は RG ごと削除)
az group create -n rg-cu-video-rag -l japaneast
az deployment group create -g rg-cu-video-rag -n cuvrag -f infra/main.bicep \
  -p baseName=cuvrag userObjectId=$(az ad signed-in-user show --query id -o tsv)
./scripts/setup_azure.sh   # .env 生成 + CU defaults へモデル紐づけ

# 2) データセット生成(TTS+画面合成。日本語研修動画 104 本 ≒ 72 分。再開可能。
#    定義を変えた動画だけ作り直し、その古い CU 結果を削除する。事前に整合性検証が走る)
uv run python -m cu_video_rag.corpus     # 値の一意性などの検証だけ行う場合
uv run python scripts/run_pipeline.py dataset

# 3) カスタム 2 段アナライザー(サブ → 親の順に作成)
uv run python scripts/run_pipeline.py create-analyzer --id segmentFieldsJa --file src/cu_video_rag/analyzer_segment_fields_ja.json
uv run python scripts/run_pipeline.py create-analyzer --id videoSearchJa --file src/cu_video_rag/analyzer_videosearch_ja.json

# 4) 解析 → 検索評価 → RAG 回答生成 → ragas → オフライン指標を一括実行(analyze はスキップ式=再開可能)
./scripts/run_full_eval.sh
# 個別に叩く場合は run_pipeline.py の docstring を参照
# (upload / analyze / cer / index / eval / rag-answer / ragas / offline-metrics)
# offline-metrics は Azure 不要(logs/ からセグメント境界一致・画面転記率・棄権率・usage/コストを再計算)

# 5) PDF レポート生成(logs/ の評価出力から数値を機械転記)
uv run python scripts/gen_report.py   # → docs/report/cu-video-rag-report.pdf

# 6) 後片付け
az group delete -n rg-cu-video-rag --yes --no-wait
# 注意: 再検証時は Foundry リソースの「同名再作成」を避ける(findings 1-8)
```

## 検証結果(2026-09-29 最新化チェック)

Azure リソースは削除済みのため、オフライン(依存更新・静的確認・logs/ からの再計算)と公式ドキュメント照合のみ。

- **依存更新**(`uv lock --upgrade`): playwright 1.62.0 → **1.63.0**(Chromium headless shell v1243 の再取得が必要)、
  推移依存(pandas 3.0.6・sqlalchemy 2.1.1・websockets 17.1 など)。据え置き: azure-search-documents 12.0.0 /
  ragas 0.4.3(いずれも最新)、langchain 0.3.30・langchain-openai 0.3.35・langchain-community 0.3.31(意図的な
  `<0.4` 上限。langchain-community 0.4 では `import ragas.llms` が `langchain_community.chat_models.vertexai`
  不在で失敗することを確認)、openai 2.54.0(langchain-openai 0.3 系の `openai<3` 制約。本ラボは直接使わない)。
  pyproject の下限を検証版に引き上げ、上限の理由をコメントに明記。ragas は私有モジュール import と非推奨ラッパー
  (`LangchainLLMWrapper`)依存のため `<0.5` を追加
- **オフライン確認**(テストスイートは無い — ライブ実測ラボ): `python -m cu_video_rag.corpus` → 104 本・111+8 問・
  problems none / `run_pipeline.py offline-metrics` を新しい依存で再実行 → `logs/` の 4 出力(segmentation /
  fact_transcription / abstention / usage_cost)が 2026-09-03 版と**バイト一致** / `gen_report.py` の HTML は
  作成日以外一致・PDF 16 ページ生成 / `ruff check` clean / `az bicep build` 警告なし
- **改修**: `record.py` の未使用 import 削除、`dev` extra(ruff)追加と lint 規則の固定(ruff 0.16 で既定ルールが
  拡張されたため 0.15 までの既定 `E4/E7/E9/F` に固定)、findings §1 見出しの重複修正と 1-1 への追記
- **変更不要と判断**: CU の GA api-version は **`2025-11-01` のまま**(whats-new 2026-09-08 版: GA は 2025-11-01、
  `2026-06-01-preview` はプレビュー。クイックスタートも「既定は GA 2025-11-01」)。`prebuilt-videoSearch` /
  基底 `prebuilt-video` と親アナライザーの config(`enableSegment`・`contentCategories` 1 カテゴリ・`omitContent`・
  `returnDetails`)は analyzer-reference 2026-09-15 版で有効、`disableFaceBlurring` は同ページの一覧に無いが
  GA SDK(azure-ai-contentunderstanding 1.1.0、既定 2025-11-01)のモデルに残る。defaults のエイリアス
  (findings 1-1)は models-deployments 2026-09-15 版で公式化。gpt-5.4-mini / text-embedding-3-small は
  service-limits 2026-09-11 版の対応モデル。Azure OpenAI の dated api-version `2024-10-21`(埋め込み・回答生成・
  ragas 判定)は廃止告知なし。azure-search-documents 12.0.0 は 2026-09-03 の実測時点で既に使用。Bicep の
  apiVersion(CognitiveServices 2025-06-01 / Search 2023-11-01 / Storage 2023-05-01)は有効
- **ライブ未検証で残るリスク**: ragas 判定の **gpt-4.1-mini はリタイア表 2026-09-21 版で Deprecated**
  (新規顧客はデプロイ不可・リタイア 2027-04-14)→ 再デプロイで `judgeModel` が通らない可能性。代替は
  温度 0 を受け付ける非 reasoning モデルに差し替え、ragas 値は再測定扱い(過去値と直接比較しない)。
  CU 出力(セグメント分割・usage)はサービス側の更新で変わりうる(findings 1-13 のとおり実行ごとにも揺れる)
- **今後の選択肢**: httpx 直叩きの代わりに CU 公式 SDK(`azure-ai-contentunderstanding` 1.1.0、GA 2025-11-01)/
  CU CLI(`cu-cli`、preview)/ Azure OpenAI の v1 API(`/openai/v1`、api-version 不要)

## 注意(このラボの割り切り)

- TTS / CU / SAS は**キー認証**(使い捨てラボの簡略化)。顧客環境では Entra ID+RBAC
  (GA で CU 専用ロール `Cognitive Service Content Understanding Owner/Contributor/Reader` あり)
- 合成データは実世界の録画よりきれい(単一話者・雑音なし・画面が鮮明)。
  CER はこの条件での**上限性能**として読む(docs/findings.md の考察参照)
