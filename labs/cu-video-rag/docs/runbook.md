# cu-video-rag 実行ガイド

> **対象:** `labs/cu-video-rag/`(Content Understanding 動画 × AI Search ハイブリッド検索 × RAG の精度検証。maf-ports のポートではない単独ラボ)
> **最終確認:** 2026-09-29 オフライン(テストスイートなし。`corpus` 検証 problems none・`offline-metrics` の再計算が 2026-09-03 版とバイト一致・レポート再生成 OK・ruff clean・`az bicep build` OK。依存 playwright 1.63.0 / azure-search-documents 12.0.0 / ragas 0.4.3 / langchain 0.3.30)/ ライブ: 2026-09-03(ラウンド 3、japaneast、CU GA API `2025-11-01`。Azure リソースは削除済み — 再デプロイ手順は §5)
> **正は本 Markdown。** 人間用 HTML(同じディレクトリの `runbook.html`)は `python3 labs/tools/build_runbooks.py` で生成する(HTML は直接編集しない)。結論と持ち帰りは [README](../README.md)、評価設計は [design.md](./design.md)、詰まりどころの全記録は [findings.md](./findings.md)、正式な結果は [レポート PDF](./report/cu-video-rag-report.pdf)。

## 1. このラボで確かめること

- CU の `prebuilt-videoSearch`(GA `2025-11-01`)の**日本語書き起こしが、別途 STT を実装しなくてよい水準か**(台本を正解にした CER)。
- **画面にしか出ない情報**(エラー番号・設定値・金額など)が検索・RAG で使えるか。素の prebuilt(構成 B)と、日本語カスタムフィールドを持つ **2 段アナライザー**(構成 C/D)を、書き起こしのみ(A0/A)と比べる(中心指標は正解動画に限定した ans@3)。
- 実装上の必須処理(**単語タイムスタンプでの再配分**・**セグメント被覆検査**)と、**研修動画 1 時間あたりの解析コスト**を実測値で持ち帰る。
- 技術選定上の意味: 「動画ナレッジの取り込みは CU で書き起こしまで賄えるが、日本語では 2 段カスタムアナライザー前提で工数を見る」([README 結論・持ち帰り](../README.md))。

## 2. 構成

図は用意していない(パイプラインはバッチスクリプトの直列実行)。流れと各段の出力:

```text
[1 データ生成・ローカル]  corpus.py(定義=正解) → Speech TTS(ja-JP) → Playwright スクショ → ffmpeg concat
                           → data/videos/*.mp4 ・ data/ground_truth/*.json(104 本)
[2 CU 解析]               upload(Blob + 読み取り SAS 3 日) → analyze
                           prebuilt-videoSearch            → logs/cu/prebuilt/<id>.json
                           videoSearchJa(親: 分割)→ segmentFieldsJa(サブ: 日本語フィールド) → logs/cu/custom/<id>.json
                           → cer(書き起こし CER → logs/cer_<tag>.json)
[3 索引]                  chunks.py(セグメント分解 + 単語再配分) → index --config A0/A/B/C/D
                           → AI Search cuvrag-<config>(ja.lucene BM25 + text-embedding-3-small HNSW、RRF)
[4 評価]                  eval(hit@k / MRR / seg_hit@1 / ans@k + 構成間 95% CI → logs/eval_*.json)
                           rag-answer(top-3 + gpt-5.4-mini) → ragas(判定 gpt-4.1-mini・温度 0)
                           offline-metrics(Azure 不要: 境界一致・画面転記率・棄権率・usage/コスト)
[5 レポート]              gen_report.py → docs/report/report.html + cu-video-rag-report.pdf
```

構成 A0〜D の中身は [design.md §3](./design.md)、2 段アナライザーが必要な理由は [findings.md §1-4](./findings.md)。

| コンポーネント | 役割 | 課金 |
| --- | --- | --- |
| ローカル(uv / Playwright / ffmpeg) | 合成研修動画 104 本(計 72.5 分)と正解の生成、チャンク化、指標計算、レポート生成 | なし |
| Foundry リソース `aif-<baseName>`(kind AIServices, S0) | CU データプレーン(`/contentunderstanding`、プロジェクト不要)+ Speech TTS + モデルデプロイの親 | CU: 動画抽出(時間課金)+ contextualization トークン / TTS: 文字数 |
| モデルデプロイ `gpt-5.4-mini`(GlobalStandard 200K TPM) | CU のセグメント分割・生成フィールド、RAG の回答生成 | トークン従量 |
| モデルデプロイ `text-embedding-3-small`(120K) | CU defaults の埋め込み、検索ベクトル | トークン従量 |
| モデルデプロイ `gpt-4.1-mini`(100K) | ragas の判定 LLM | トークン従量 |
| Storage(Standard_LRS、`videos` コンテナ) | mp4 置き場(CU へは SAS URL で渡す) | 容量(僅少) |
| AI Search basic | インデックス `cuvrag-a0` / `-a` / `-b` / `-c` / `-d` | **稼働時間課金(約 $0.133/時)— 放置しない** |

## 3. 前提

| 区分 | 必要なもの | 備考 |
| --- | --- | --- |
| ツール | uv(Python 3.11 以上。uv が取得。検証は 3.13) | オフライン確認はこれだけ(+ レポート再生成に Chromium) |
| ツール(データ生成・レポート) | Playwright Chromium(`uv run playwright install chromium`)、ffmpeg(PATH 上)、日本語フォント(Noto Sans CJK JP 等) | playwright の版を上げたらブラウザも取り直す(§9) |
| ツール(ライブ) | Azure CLI(`az deployment` / `az storage` / `az search`) | `upload` は `az storage blob upload-batch` を呼ぶ |
| Azure(ライブのみ) | 使い捨て RG(japaneast)に [infra/main.bicep](../infra/main.bicep) をデプロイ | 課金あり。GlobalStandard のクォータ(gpt-5.4-mini 200K TPM ほか)が必要 |
| 権限 | RG への Contributor + ロール割り当て権限(Bicep が署名ユーザーに Cognitive Services OpenAI User / Cognitive Services User / Storage Blob Data Contributor を付与) | ラボ本体はキー認証(TTS / CU / Search / SAS)。顧客環境では Entra ID + RBAC にする([README 注意](../README.md)) |

環境変数(`labs/cu-video-rag/.env`。**`scripts/setup_azure.sh` がデプロイ出力とキーから生成する**。雛形ファイルは無い。キーを含むので共有しない・git 管理外):

| 変数 | 用途(使うサブコマンド) | 取得元 |
| --- | --- | --- |
| `FOUNDRY_ENDPOINT` | CU の呼び出し先(defaults / create-analyzer / analyze) | main.bicep 出力 `foundryEndpoint` |
| `AOAI_ENDPOINT` | 埋め込み・回答生成・ragas(`https://<sub>.cognitiveservices.azure.com`、アカウント直。プロジェクト経由の embeddings は 404 — foundry-probes 08) | main.bicep 出力 `aoaiEndpoint` |
| `AI_KEY` | Foundry リソースのキー(TTS・CU・モデル呼び出しすべて) | `az cognitiveservices account keys list` |
| `REGION` | TTS のリージョン(dataset)。setup_azure.sh は `japaneast` 固定 | 固定値 |
| `STORAGE_NAME` / `STORAGE_KEY` | Blob アップロードと SAS 生成(upload) | main.bicep 出力 `storageName` / `az storage account keys list` |
| `SEARCH_ENDPOINT` / `SEARCH_ADMIN_KEY` | インデックス作成・検索(index / eval / rag-answer) | main.bicep 出力 `searchEndpoint` / `az search admin-key show` |
| `COMPLETION_MODEL` / `COMPLETION_DEPLOYMENT` | defaults 登録のモデル名 / デプロイ名、回答生成のデプロイ | 固定値 `gpt-5.4-mini` |
| `EMBED_MODEL` / `EMBED_DEPLOYMENT` | defaults 登録、検索ベクトル、ragas の埋め込み | 固定値 `text-embedding-3-small` |
| `JUDGE_DEPLOYMENT` | ragas の判定 LLM | 固定値 `gpt-4.1-mini` |
| `RG` / `FOUNDRY_NAME` | 記録用(コードは読まない) | setup_azure.sh の `RG`(既定 `rg-cu-video-rag`)/ 出力 `foundryName` |

setup_azure.sh 自体は `RG`(既定 `rg-cu-video-rag`)と `DEP`(デプロイ名、既定 `cuvrag`)を環境変数で上書きできる。

## 4. オフライン実行(Azure 不要・無料)

このラボにテストスイートは無い(ライブ実測が本体)。オフラインで確かめられるのは、正解データの整合性・保存済みログからの指標再計算・レポート再生成・lint:

```bash
cd labs/cu-video-rag
uv sync --extra dev
uv run ruff check .                                   # 期待: All checks passed!
uv run python -m cu_video_rag.corpus                  # 期待: 下の出力例(problems: none)
uv run python scripts/run_pipeline.py offline-metrics # logs/ がある環境のみ(logs/ は git 管理外)
uv run playwright install chromium                    # 初回・playwright 更新時のみ
uv run python scripts/gen_report.py                   # logs/ 必須。docs/report/ の HTML・PDF を上書き(作成日が今日になる)
```

`corpus` の期待出力(2026-09-29 実行):

```text
scenarios: 104 Counter({'narrated': 88, 'silent': 10, 'slide': 5, 'long': 1})
queries: 111 Counter({'S': 61, 'N': 42, 'C': 8}) + unanswerable 8
problems: none
```

オフラインで確認できる主な挙動:

- [ ] `corpus.validate()` が「S クエリの回答値が他の動画の台本・画面に(部分文字列としても)現れない」ことを機械検証して `problems: none`([findings 1-11](./findings.md))
- [ ] `offline-metrics` の再計算が記録値と一致: 画面転記率 custom `found_any 1.0`(67/67)/ prebuilt `0.179`、棄権率 U は A・C とも `1.0`、`total variable: 8.1626`(2026-09-29 に依存更新後の環境で 4 ファイルともバイト一致を確認)
- [ ] `gen_report.py` がレポートを再生成できる(HTML は作成日以外一致、PDF 16 ページ)。数値は logs/ からの機械転記なので手で直さない

ライブ評価をしていない環境(新しく clone した直後など)では logs/ が無いため、`offline-metrics` は空の集計に、`gen_report.py` は `missing .../logs/... — 評価を先に実行してください` で止まる。

## 5. ライブ実行(Azure 必要・課金あり)

実測時の規模(104 本 × 2 アナライザー + 検索 5 構成 + ragas 2 構成)で、CU 解析 1 巡 ≈ $7、全体 ≈ $8〜12 が目安(§6 の判定基準・[README 結論](../README.md))。

### 5.1 デプロイ

```bash
cd labs/cu-video-rag
uv sync --extra dev && uv run playwright install chromium
az group create -n rg-cu-video-rag -l japaneast
# baseName は前回と別名にする(同名の再作成は CU が壊れる — findings 1-8)
az deployment group create -g rg-cu-video-rag -n cuvrag -f infra/main.bicep \
  -p baseName=<新しい名前> userObjectId=$(az ad signed-in-user show --query id -o tsv)
./scripts/setup_azure.sh    # .env 生成 + CU defaults へモデルを紐づけ(= run_pipeline.py defaults)
```

Bicep パラメータ: `baseName`(必須)/ `userObjectId`(必須)/ `location`(既定 RG のリージョン)/ `completionModel`・`completionVersion`(既定 `gpt-5.4-mini` / `2026-03-17`)/ `embeddingModel`・`embeddingVersion`(`text-embedding-3-small` / `1`)/ `judgeModel`・`judgeVersion`(`gpt-4.1-mini` / `2025-04-14`)。出力: `foundryName` / `foundryEndpoint` / `aoaiEndpoint` / `storageName` / `searchName` / `searchEndpoint`。

`defaults` の登録内容は `gpt-5.4-mini` / `text-embedding-3-small`(モデル名 → デプロイ名)に加えて、prebuilt が参照する**エイリアス** `prebuilt-analyzer-completion-mini` / `prebuilt-analyzer-embedding`(findings 1-1)。GA 版で失敗したときだけ `2026-06-01-preview` で再試行する実装。defaults とカスタムアナライザーは**データプレーンの状態**なので、環境を作り直したら毎回やり直す(findings 1-7)。

### 5.2 実行(データ生成 → CU 解析 → 索引 → 評価 → レポート)

```bash
# 1) データ生成(TTS + 画面合成。再開可能。定義を変えた動画だけ作り直し、その古い CU 結果を削除する)
uv run python scripts/run_pipeline.py dataset

# 2) カスタム 2 段アナライザーを作成(サブ → 親の順。親がサブを参照するため)
uv run python scripts/run_pipeline.py create-analyzer --id segmentFieldsJa --file src/cu_video_rag/analyzer_segment_fields_ja.json
uv run python scripts/run_pipeline.py create-analyzer --id videoSearchJa --file src/cu_video_rag/analyzer_videosearch_ja.json

# 3) upload → analyze ×2 → cer → index A0/A/B/C/D → eval → rag-answer A,C → ragas A,C → offline-metrics
./scripts/run_full_eval.sh 2>&1 | tee logs/full_eval.log   # 最後に ALL_DONE

# 4) レポート(logs/ から機械転記)
uv run python scripts/gen_report.py                         # → docs/report/cu-video-rag-report.pdf
```

個別に叩くときのサブコマンド(`scripts/run_pipeline.py`):

| サブコマンド | 主な引数 | 出力 |
| --- | --- | --- |
| `upload` | — | Blob へ一括アップロード、`data/eval/video_urls.json`(SAS 付き URL、期限 3 日) |
| `analyze` | `--analyzer`(既定 `prebuilt-videoSearch`)`--tag`(既定 `prebuilt`)`--parallel 4` `--only <id>` `--force` | `logs/cu/<tag>/<id>.json`(既存はスキップ = 再開可能)、`logs/timings_<tag>.json` |
| `cer` | `--tag` | `logs/cer_<tag>.json` |
| `index` | `--config`(A0 / A / B / C / D。`--tag` で解析結果の系統を上書き可) | インデックス `cuvrag-<config>`(毎回削除 → 再作成) |
| `eval` | `--configs A0,A,B,C,D` | `logs/eval_<config>.json`、`logs/eval_compare.json`(対応ありブートストラップ 95% CI) |
| `rag-answer` / `ragas` | `--config` | `logs/rag_answers_<config>.json` / `logs/ragas_<config>.json` |
| `offline-metrics` | — | `logs/segmentation.json` / `fact_transcription.json` / `abstention.json` / `usage_cost.json` |

所要時間の目安(2026-09-03 のログ): 解析は 1 本あたり中央値 31 秒(prebuilt)/ 41 秒(カスタム)で、`--parallel 4` なら 104 本で 1 アナライザーあたり十数分。ragas は 1 構成 555 ジョブで約 17 分。

期待される出力の例(`logs/full_eval3.log` から抜粋。値は実行ごとに変わる):

```text
=== analyze prebuilt ===
analyzing 26 videos with prebuilt-videoSearch (parallel=4)
  done vpn-setup: 41.2s, segments=6, retries=0
=== cer ===
{"micro_cer": 0.0173, "missing": []}          # prebuilt(再解析分 26 本)
{"micro_cer": 0.0044, "missing": []}          # custom
=== index ===
config C: uploaded 312/312 chunks (embedding tokens 70451)
=== retrieval eval ===
| 構成 | 対象 | n | hit@1 | hit@3 | MRR | seg_hit@1 | ans@1 | ans@3 |
| A | 全体 | 111 | 0.622 | 0.865 | 0.727 | 0.495 | 0.000 | 0.000 |
| C | 全体 | 111 | 0.730 | 0.937 | 0.826 | 0.595 | 0.557 | 0.672 |
[A->C] {'hit@1': '+0.108 [+0.009,+0.207]*', ...}
config C (n=111):
  context_recall: 0.8018
  answer_correctness: 0.5894
abstention[C]: {'n': 8, 'abstain_rate': 1.0, 'answered_anyway': []} / answerable {'n': 111, 'abstain_rate': 0.297}
ALL_DONE
```

### 5.3 判定基準(再測定で「再現できた」と見なす水準)

値は 2026-09-03 ラウンド 3 の記録([findings.md §0](./findings.md) / レポート §7〜10)。合成データでも CU の出力は実行ごとに揺れる(findings 1-13)ので、数値の一致ではなく**大小関係と桁**を見る。

| 段階 | 指標(出力ファイル) | 記録値 | 合否の見方 |
| --- | --- | --- | --- |
| データ生成 | `corpus.validate()` | problems none | 1 件でもあれば `dataset` が停止する(不合格) |
| CU 解析 | `analyze` の failed | 0 本 | failed があると exit 1。§9 で原因を切り分けて `--only <動画 id>` で再解析 |
| 書き起こし | CER micro(`logs/cer_<tag>.json`、94 本) | custom 0.44% / prebuilt 1.34% | 1% 前後なら合格。1 本だけ極端に悪い場合は先頭・末尾欠落(findings 1-13)を疑う |
| 検索 | hit@3 全 111 問(`logs/eval_*.json`) | A 0.865 / C 0.937 | C ≥ A |
| 検索(画面のみ S 61 問) | ans@3(正解動画限定) | A 0.000 / B 0.115 / C 0.672 / D 0.689 | **A が 0 のまま**(書き起こしに値が無い)かつ C が大きく上回る。A が 0 でなければ評価データへの値の漏れ(findings 1-11) |
| CU 出力 | 画面転記率 `found_any`(`logs/fact_transcription.json`、67 件) | custom 1.0 / prebuilt 0.179 | custom がほぼ全件 |
| CU 出力 | セグメント境界 ±2 秒・被覆(`logs/segmentation.json`、custom) | precision 0.942 / recall 0.605 / `coverage_min` 0.798 / `videos_with_head_gap_over_3s` 0 | 先頭欠落 3 秒超の動画が出たら再解析 |
| RAG | 棄権率(`logs/abstention.json`) | U 8 問は A・C とも 1.0、正解あり質問は A 0.568 → C 0.297 | U が 1.0 未満なら捏造(`answered_anyway` を確認) |
| RAG | ragas(`logs/ragas_C.json`) | context_precision 0.73 / context_recall 0.80 / answer_correctness 0.59 | C > A。判定 LLM に依存する相対比較として読む。answer_relevancy は参考値 |
| コスト | `logs/usage_cost.json` | 104 本 1 回で prebuilt $3.39 / custom $3.61(1 時間あたり $2.68 / $2.85) | 桁が同じ。単価は `cost.py` の `PRICES_USD`(2026-09-03 取得)なので見積もり時は最新を確認 |

## 6. 確認観点

| 確認 | # | 観点 | 確認方法 | 期待結果 |
| --- | --- | --- | --- | --- |
| [ ] | 1 | 正常系: 正解データの整合性 | `uv run python -m cu_video_rag.corpus`、`dataset` 後に `data/videos/` と `data/ground_truth/` のファイル数 | `problems: none`、mp4 と `data/ground_truth/*.json` が 104 本ずつ |
| [ ] | 2 | 正常系: CU の前提設定 | `setup_azure.sh` の末尾出力(defaults の GET) | `modelDeployments` にモデル名 2 つ + エイリアス 2 つ(`prebuilt-analyzer-completion-mini` / `prebuilt-analyzer-embedding`) |
| [ ] | 3 | 正常系: 解析が全件通る | `run_full_eval.sh` の analyze 行、`ls logs/cu/prebuilt logs/cu/custom` | `FAILED` なし、各 104 JSON。`retries` が多いなら TPM 不足(findings 1-6) |
| [ ] | 4 | パターン固有: 2 段アナライザーでフィールドが出る | `logs/cu/custom/vpn-setup.json` のセグメント `contents[]` を開く | 各セグメントに `summaryJa`(日本語)・`screenTexts`(例: `vpn.contoso-jp.example`・`エラー 809`)・`uiActions` がある。prebuilt 側は英語 `Summary` のみ |
| [ ] | 5 | パターン固有: 画面のみ情報が検索で取れる | `eval` の表(タイプ S の ans@3)と `logs/fact_transcription.json` | A 0.000 / C ≈0.67、custom の転記率 ≈1.0(§5.3) |
| [ ] | 6 | 分岐・異常系: 発話の欠落を検知できる | `offline-metrics` の `transcript divergence` 行と `segmentation.json` の `videos_with_head_gap_over_3s` | 乖離動画(実測時は password-reset・g67-portal-cancel)を列挙できる。欠落動画は `analyze --analyzer <id> --tag <tag> --only <動画 id> --force` で再解析 |
| [ ] | 7 | 分岐・異常系: 根拠が無い質問で捏造しない | `logs/abstention.json` | U 8 問の `abstain_rate` 1.0、`answered_anyway` が空 |
| [ ] | 8 | 観測: 処理時間とトークンの記録 | `logs/timings_<tag>.json`(秒・セグメント数・リトライ・usage)と `logs/usage_other.json` | 全動画に `usage`(`videoHours` / `contextualizationTokens` / `tokens`)が入り、`offline-metrics` のコスト集計が出る |
| [ ] | 9 | コスト・後片付け | §8 の削除後に `az group show -n rg-cu-video-rag`、翌日以降 Cost Management | RG が消えている(AI Search の時間課金が止まる)。実課金が usage 概算と桁で一致 |

## 7. トレース・評価の確認

OTel トレースは組み込んでいない(バッチ評価スクリプトで、観測は `logs/` の JSON — timings・usage・eval・ragas — で行う)。評価は §5.3 の各ファイルと [レポート PDF](./report/cu-video-rag-report.pdf) で確認する。

## 8. 片付け

```bash
az group delete -n rg-cu-video-rag --yes --no-wait   # AI Search basic が時間課金なので検証後すぐ消す
rm -f .env                                           # キー入り。残すならキーを再生成(az cognitiveservices account keys regenerate 等)
```

- Foundry リソースはソフト削除になる。**次の検証は `baseName` を変えて別名で作る**(パージ → 同名再作成すると CU の解析が 404 で失敗し続けた — findings 1-8)。
- `data/`(mp4・音声・画面)と `logs/` はローカルに残る(git 管理外)。再解析しない限りレポートの再生成・`offline-metrics` はこのままできる。

## 9. トラブルシューティング

| 症状 | 原因 | 対処 |
| --- | --- | --- |
| analyze が `Failed`: `This analyzer needs a 'completion' model deployment ... none was resolved` | defaults にエイリアス未登録(1-1)/ 環境を作り直した後の defaults 未登録(1-7)/ カスタム定義で `models.completion` 省略(1-5) | `run_pipeline.py defaults` を再実行。カスタム定義の `models.completion` を確認。エラーは PATCH 時ではなく analyze 時に出る |
| `create-analyzer` が 400(`InvalidBaseAnalyzerId` / `omitContent ... has fields` / `segmentationDefinition must be provided`) | 基底にできるのは `prebuilt-video` 等 4 つだけ、`omitContent` とフィールドは併用不可、分割は `contentCategories` で定義(1-2) | リポジトリの 2 つの JSON 定義をそのまま使う |
| 定義を変えて `create-analyzer` したのに結果が変わらない | 既存 ID への PUT は成功応答なのに反映されない(1-3) | 削除してから作り直す: `uv run python -c "import os,sys; sys.path.insert(0,'src'); from dotenv import load_dotenv; load_dotenv('.env'); from cu_video_rag.cu_client import CuClient; CuClient(os.environ['FOUNDRY_ENDPOINT'], os.environ['AI_KEY']).delete_analyzer('videoSearchJa')"` |
| カスタムフィールドが結果のどこにも出ない | 親の `fieldSchema` はセグメントに適用されない(1-4) | サブ(`segmentFieldsJa`)にフィールドを持たせ、親の `contentCategories.segment.analyzerId` から参照する |
| analyze が `RateLimit, 429` で Failed | CU ではなく紐づけた補完デプロイの TPM 不足(1-6) | `--parallel` を下げる / TPM を増やす(Bicep 既定 200K)。スクリプトは 5 回まで指数バックオフで再試行する |
| analyze が `(NotFound, 404, The Azure OpenAI deployment or resource was not found.)` のまま直らない | ソフト削除 → パージ → 同名再作成したアカウント(1-8) | 別名の `baseName` で作り直す |
| 同名で作り直そうとして `FlagMustBeSetForRestore` | Foundry リソースがソフト削除中 | パージではなく別名で作る(上の行) |
| 1 本だけ CER が極端に悪い / 書き起こしの先頭・末尾が欠ける | セグメントが動画の先頭・末尾を覆わず発話が消える(実行ごとに揺れる、1-13) | `analyze --analyzer <アナライザー> --tag <tag> --only <動画 id> --force` で再解析(prebuilt なら `prebuilt-videoSearch` / `prebuilt`、カスタムなら `videoSearchJa` / `custom`)。取り込み実装では被覆検査を入れる |
| seg_hit@1 が低い / 書き起こしが空のセグメントが多い | transcriptPhrases は開始時刻のセグメントに丸ごと付く(1-10) | 構成 A 以降は `chunks.resplit_transcripts` で再配分済み。A0 は影響測定用にわざと未適用 |
| 書き起こしのみ(A)で ans@3 が 0 でない | 回答値が他の動画にも出ている(1-11) | `python -m cu_video_rag.corpus` の problems を確認して定義を直し、`dataset` を再実行 |
| `analyze` で動画を取得できない | SAS の期限(3 日)切れ | `upload` を再実行して URL を作り直す |
| ragas のログに `DeploymentNotFound 404`、answer_relevancy に NaN | 実測時も一部ジョブで発生(A 9 件・C 13 件が NaN。平均は NaN を除いて計算) | `JUDGE_DEPLOYMENT` / `EMBED_DEPLOYMENT` を確認。デプロイ直後なら数分待って `ragas --config <C>` だけ再実行 |
| `judgeModel`(gpt-4.1-mini)のデプロイが通らない | リタイア表 2026-09-21 版で Deprecated(新規顧客はデプロイ不可、リタイア 2027-04-14) | 温度 0 を受け付ける非 reasoning モデルに `judgeModel` / `judgeVersion` と `.env` の `JUDGE_DEPLOYMENT` を差し替える。ragas 値は再測定扱い(過去値と直接比べない) |
| `gen_report.py` が `Executable doesn't exist at .../chromium_headless_shell-XXXX` | playwright を上げた後にブラウザ未取得 | `uv run playwright install chromium` |
| `missing env: X (scripts/setup_azure.sh を先に実行)` | `.env` が無い・古い | `./scripts/setup_azure.sh`(`RG` / `DEP` を合わせる) |

## 10. 関連・更新履歴

- 結論・持ち帰り・最新化チェックの記録: [README](../README.md)
- 評価設計(データ・構成 A0〜D・指標): [design.md](./design.md) / 詰まりどころ 13 件と定量結果: [findings.md](./findings.md) / データセット調査: [dataset-research.md](./dataset-research.md)
- 要件シナリオ(文書・動画処理): [casebook S-09](../../../docs/survey/casebook/01-scenario-playbook.md#s-09-文書・動画処理-idp) / 詰まりどころ索引 P-D01〜P-D03: [casebook L. 文書処理と音声](../../../docs/survey/casebook/02-pitfalls-index.md#l-文書処理と音声)
- Content Understanding の GA / プレビュー状況: [features 07 Foundry Tools](../../../docs/survey/features/07-foundry-tools.md)

| 日付 | 内容 |
| --- | --- |
| 2026-09-29 | 初版(依存更新 playwright 1.63.0 ほか、ragas / langchain の上限に理由を明記、`dev` extra に ruff。CU GA api-version は `2025-11-01` のまま変更不要) |
