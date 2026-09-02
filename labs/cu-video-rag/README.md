# cu-video-rag — Content Understanding video × AI Search の精度検証ラボ

ナレーション付き画面操作研修動画を **Azure AI Content Understanding の
`prebuilt-videoSearch`(GA API `2025-11-01`)** で解析し、AI Search の
ハイブリッド検索に取り込んだときの精度を、**書き起こし(CER)と RAG 検索
(hit@k / MRR)の 2 段階で定量評価**する検証ラボ。

背景: helpdesk 案件で「社内ナレッジに画面操作の研修動画が含まれる場合に取り込みたい」
という要件が想定され、CU ベースの方式(書き起こしを別途実装しない)の実力を
実測で確かめる必要があった。

## 結論(実測サマリ 2026-09-02)

自作合成の日本語研修動画 5 本(計 5.3 分。日本語オープンデータセット不在のため —
[調査](./docs/dataset-research.md))+評価クエリ 20 問で実測:

| 何を測ったか | 結果 |
|---|---|
| 書き起こし CER(正解=台本、正規化後 1,418 文字) | **1.13%**(実質誤認識は同音のドメイン語 5 箇所のみ。合成音声での上限性能) |
| 正解動画ヒット hit@3(全 4 構成) | **1.000** |
| 回答値がチャンクに含まれる率 ans@3(画面のみ情報 6 問) | 書き起こしのみ **0.000** / prebuilt 素 **0.167** / **カスタムフィールド 1.000** |
| 画面のみ情報(アドレス・エラー番号・金額等、25〜40px 表示)の転記 | **6/6 件成功**(1 FPS・512×512 縮小でも読めた) |
| 解析時間 | 動画実時間の約 0.7〜2 倍/本 |

**持ち帰り**: ①CU の日本語書き起こしは別途 STT を実装する必要がない水準。
②prebuilt-videoSearch を**素のまま**日本語 RAG に使うとセグメント記述が英語で返り
ランキングをむしろ悪化させる(hit@1 1.000→0.900)。**日本語カスタムフィールド
(日本語要約+画面内テキスト転記)が実質必須**で、これには**サブアナライザー参照の
2 段構成**が必要(親の fieldSchema はセグメントに適用されない)。
③画面にしか出ない情報も大きめの文字なら拾えて検索可能になる。
詳細・試行錯誤の過程は [docs/findings.md](./docs/findings.md)。

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

```bash
# 0) 依存(初回のみ)
uv sync && uv run playwright install chromium

# 1) 基盤(課金発生。検証後は RG ごと削除)
az group create -n rg-cu-video-rag -l japaneast
az deployment group create -g rg-cu-video-rag -n cuvrag -f infra/main.bicep \
  -p baseName=cuvrag userObjectId=$(az ad signed-in-user show --query id -o tsv)
./scripts/setup_azure.sh   # .env 生成 + CU defaults へモデル紐づけ

# 2) データセット生成(TTS+画面合成。日本語研修動画 5 本 ≒ 5.3 分)
uv run python scripts/run_pipeline.py dataset

# 3) 解析 → 評価
uv run python scripts/run_pipeline.py upload
uv run python scripts/run_pipeline.py analyze                  # prebuilt-videoSearch
uv run python scripts/run_pipeline.py cer --tag prebuilt       # 書き起こし CER
# カスタム 2 段アナライザー(サブ → 親の順に作成)
uv run python scripts/run_pipeline.py create-analyzer --id segmentFieldsJa --file src/cu_video_rag/analyzer_segment_fields_ja.json
uv run python scripts/run_pipeline.py create-analyzer --id videoSearchJa --file src/cu_video_rag/analyzer_videosearch_ja.json
uv run python scripts/run_pipeline.py analyze --analyzer videoSearchJa --tag custom
for c in A B C D; do uv run python scripts/run_pipeline.py index --config $c; done
uv run python scripts/run_pipeline.py eval --configs A,B,C,D   # 検索評価

# 4) 後片付け
az group delete -n rg-cu-video-rag --yes --no-wait
```

## 注意(このラボの割り切り)

- TTS / CU / SAS は**キー認証**(使い捨てラボの簡略化)。顧客環境では Entra ID+RBAC
  (GA で CU 専用ロール `Cognitive Service Content Understanding Owner/Contributor/Reader` あり)
- 合成データは実世界の録画よりきれい(単一話者・雑音なし・画面が鮮明)。
  CER はこの条件での**上限性能**として読む(docs/findings.md の考察参照)
