# foundry-probes 実行ガイド

> **対象:** `labs/foundry-probes/`(Foundry 機能の挙動確認 probe 9 本。アプリではなく「観点ごとにリクエストを投げて生の応答を記録する」ラボ)
> **最終確認:** 2026-09-29 オフライン(自動テストなし。9 本の `py_compile`・`ruff check` clean・SDK 呼び出しの AST シグネチャ照合で不一致 0。依存 openai 3.20.0 / azure-ai-projects 2.7.0)/ ライブ: 2026-08-04(japaneast・gpt-5.4-mini v2026-03-17・当時は openai 2.53.0 / azure-ai-projects 2.4.0。Azure リソースは削除済み — 再デプロイ手順は §5)
> **正は本 Markdown。** 人間用 HTML(同じディレクトリの `runbook.html`)は `python3 labs/tools/build_runbooks.py` で生成する(HTML は直接編集しない)。発見の一次記録は各 probe の `NOTES.md`、一覧と検証対象外の理由は [README](../README.md)。

## 1. このラボで確かめること

- maf-ports の 13 ポートに乗らなかった Foundry 機能(Conversations・prompt agents・File Search・Web search・Model router・Structured outputs・ガードレール・埋め込みのルーティング・継続評価)が、**単純な入力に対して実際にどう振る舞うか**。
- 各 probe は観点(A, B, C…)ごとに「リクエスト → 応答の要点」を対で標準出力に出す。**失敗(`!!` 行)も観察結果**で、スクリプトは例外で止まらず次の観点に進む。
- 出力(`logs/<probe>.log`)が `NOTES.md` の根拠になる。再実測では「NOTES の発見と同じ形が出るか / 変わったか」を見る。

## 2. 構成

図(`architecture.png`)は本ラボには未作成(probe はクライアントから Foundry の各 API を直接叩くだけで、構成要素間の流れがない)。

```text
probes/NN-*/probe.py ──(Entra ID: az login / DefaultAzureCredential)──┬─▶ プロジェクト openai/v1  {project}/openai/v1        … 01〜07, 09
                                                                      ├─▶ エージェントエンドポイント {project}/agents/<name>/endpoint/protocols/openai … 02, 09
                                                                      ├─▶ プロジェクト REST(agents / evaluation_rules) … 02, 09
                                                                      └─▶ アカウント openai/v1  https://<foundry>.openai.azure.com/openai/v1 … 01(A), 08
```

| コンポーネント | 役割 | 課金 |
| --- | --- | --- |
| probe スクリプト(ローカル、`uv run python ...`) | 観点別リクエストと結果表示 | なし |
| Foundry リソース `aif-<baseName>` + プロジェクト `probes`(`infra/main.bicep`) | 全 probe の接続先 | リソース自体は無料 |
| モデルデプロイ gpt-5.4-mini(GlobalStandard, cap 10) | 01〜07, 09 の推論 | トークン従量 |
| model-router デプロイ(`deployRouter=true` 時) | 01(G)・05 | ルーティング先モデルの単価で従量 |
| text-embedding-3-small(CLI で追加) | 08 | トークン従量 |
| File Search のベクトルストア | 03(probe 内で作成・削除) | ストレージ従量(削除忘れ注意) |
| Web search ツール | 04 | ツール呼び出し単位の別課金・**DPA 対象外** |
| Log Analytics + Application Insights(接続済み) | 09 の継続評価結果・手動 KQL | 取り込み従量 |

## 3. 前提

| 区分 | 必要なもの | 備考 |
| --- | --- | --- |
| ツール | uv(Python 3.11 以上。uv が取得)、Azure CLI(`az login` 済み) | オフライン確認は uv だけ |
| Azure | `infra/main.bicep` + `infra/roles.bicep` + 埋め込みデプロイ(§5.1) | 課金あり。使い終わったら RG ごと削除 |
| 権限 | 署名ユーザーに Cognitive Services OpenAI User + Foundry User(旧 Azure AI User)— main.bicep が付与。プロジェクト/アカウント MI に同 2 ロール — roles.bicep が付与(09 の継続評価の前提) | RBAC 伝播に 5〜15 分 |
| データ取り扱い | 04 は検索クエリが Microsoft のコンプライアンス境界外(Bing)へ出る。05 は既定で非 OpenAI モデル(Grok 等)へ流れる | 機微データを入力しない |

環境変数(`labs/foundry-probes/.env`。雛形は `.env.example`。**ライブ実行時のみ必要**。`.env` は git 管理外):

| 変数 | 用途 | 取得元 |
| --- | --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | プロジェクト経由の openai client / agents / evaluation_rules | main.bicep 出力 `projectEndpoint` |
| `FOUNDRY_OPENAI_V1_ENDPOINT` | アカウント直下の openai/v1(01 の A、08) | main.bicep 出力 `openaiV1Endpoint` |
| `FOUNDRY_MODEL` | 推論モデルのデプロイ名 | main.bicep 出力 `modelDeploymentName`(例 `gpt-5.4-mini`) |
| `FOUNDRY_API_KEY` | 空なら Entra ID(既定・推奨)。アカウント openai/v1 にだけ効く | ポータルのキー(通常は空のまま) |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | probe のコードは使わない(手動 KQL 用のメモ) | main.bicep 出力 `appInsightsConnectionString` |

## 4. オフライン確認(Azure 不要・無料)

probe はライブ専用スクリプトで、自動テスト(pytest)はない。オフラインでは「現行 SDK で読み込めて、呼び出しの形が合っているか」までを確認する。

```bash
cd labs/foundry-probes
uv sync
uv run ruff check .                                          # 期待: All checks passed!
for f in probes/*/probe.py; do uv run python -m py_compile "$f" || echo "NG $f"; done   # 期待: 何も出ない
uv run python -c "from foundry_probes.common import Settings, make_project_client; print('import ok')"
```

オフラインで確認済みの事項(2026-09-29):

- [ ] 全 probe の `client.<...>.create(...)` 等の呼び出し先とキーワード引数が openai 3.20.0 / azure-ai-projects 2.7.0 のシグネチャに存在する(AST 照合で不一致 0)
- [ ] `get_openai_client()` → `{project}/openai/v1/`、`get_openai_client(agent_name=...)` → `{project}/agents/<name>/endpoint/protocols/openai/` を向く(`Settings` にダミー値を入れて生成した client の `base_url` で確認)
- [ ] 09 の `EvaluationRule(...)` がワイヤ形式 `{"eventType": "responseCompleted", "filter": {"agentName": ...}, "action": {"type": "continuousEvaluation", ...}}` にシリアライズされる
- [ ] `az bicep build --file infra/main.bicep --stdout > /dev/null`(roles.bicep も)が警告なしで通る

## 5. ライブ実行(Azure 必要・課金あり)

### 5.1 デプロイ

```bash
cd labs/foundry-probes
az group create -n rg-foundry-probes -l japaneast
az deployment group create -g rg-foundry-probes -f infra/main.bicep \
  -p baseName=fprobes modelName=gpt-5.4-mini modelVersion=2026-03-17 \
     userObjectId=$(az ad signed-in-user show --query id -o tsv) \
     deployRouter=true routerVersion=2025-11-18
# 第 2 段: MI へのロール(principalId ローテーション対策で分離)
PID=$(az rest --method get --url "https://management.azure.com$(az cognitiveservices account show -n aif-fprobes -g rg-foundry-probes --query id -o tsv)/projects/probes?api-version=2025-06-01" --query identity.principalId -o tsv)
AID=$(az cognitiveservices account show -n aif-fprobes -g rg-foundry-probes --query identity.principalId -o tsv)
az deployment group create -g rg-foundry-probes -f infra/roles.bicep -p baseName=fprobes accountPrincipalId=$AID projectPrincipalId=$PID
# 08 用の埋め込みデプロイ
az cognitiveservices account deployment create -n aif-fprobes -g rg-foundry-probes \
  --deployment-name text-embedding-3-small --model-name text-embedding-3-small --model-version 1 \
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10
```

`main.bicep` の出力(`projectEndpoint` / `openaiV1Endpoint` / `modelDeploymentName`)を `.env` に転記する(`cp .env.example .env` してから編集)。

### 5.2 実行

```bash
uv sync
./run_all.sh                                          # 全 9 本を順に実行し logs/<probe>.log に保存(tee で画面にも出る)
uv run python probes/05-model-router/probe.py         # 1 本だけ(例)
```

出力の読み方: `== <観点>` が見出し、`--- <ラベル>` の下が観察値(長文は `…(全N文字)` で切り詰め)、`!! <例外型>: <内容>` はその観点で返ったエラー(観察対象。スクリプトは続行する)。

## 6. probe 別の確認ポイント

各節の「期待(2026-08-04 実測)」は NOTES の記録。**値(id・トークン数・ルーティング先)は実行ごとに変わる**ので形で比べる。

### 6.1 01 Conversations API

- **確かめること**: サービス側会話状態の使えるサーフェス、多ターン継続、items の粒度、`store=False` との併用、別モデルでの継続、エラー形。
- **コマンド**: `uv run python probes/01-conversations/probe.py`
- **出力で見る所**: A で `!! NotFoundError ... 404`(アカウント直下は不可)、A' で `conv_...` が作成される / C の turn2 が「青」/ F が `items 件数: 0` / G の「実際に使われたモデル」/ H が 400 `Malformed identifier`。
- **主要な発見**: Conversations は**プロジェクト経由のみ**。会話に TTL フィールドはなく明示削除まで残る。`store=False` を conversation と同時指定するとそのターンは会話に残らない(エラーも出ない)。
- 詳細: [01 NOTES](../probes/01-conversations/NOTES.md)

### 6.2 02 Prompt agents

- **確かめること**: `agents.create_version` の版採番、エージェントエンドポイント経由の呼び出し、conversation との組み合わせ、function ツールの返り先、`instructions` 上書き、削除。
- **コマンド**: `uv run python probes/02-prompt-agents/probe.py`
- **出力で見る所**: A の `"id": "probe-prompt-agent:1"` と `instance_identity`(エージェントごとの Entra ID)/ B で `v1.version=1 -> v2.version=2` / D が川柳で返る(既定は最新版)/ F の最終 item が `function_call` / G が `!! BadRequestError ... Not allowed when agent is specified`。
- **主要な発見**: 版は自動採番の upsert(typo が新エージェントになる)。function ツールはクライアント実行ループ。呼び出し時の `instructions` 上書きは 400。エンドポイントの既定ルーティングは「常に最新版」(公式 configure-agent 2026-09-11 版とも一致)。
- 詳細: [02 NOTES](../probes/02-prompt-agents/NOTES.md)

### 6.3 03 File Search + ベクトルストア

- **確かめること**: ファイル登録・ベクトルストアのチャンク既定値・インデックス待ち・根拠付き回答と引用・明示 TTL・削除時のファイル残存。
- **コマンド**: `uv run python probes/03-file-search/probe.py`
- **出力で見る所**: B の `chunking_strategy` が `max_chunk_size_tokens: 800 / chunk_overlap_tokens: 400` / C が数秒で `status=completed` / D が「3 年間」/ E に `file_citation` / F に `expires_at` が入る / G で「store 削除後もファイルは残る」。
- **主要な発見**: 埋め込みモデルの自前デプロイ不要(サービス管理・変更不可)。自作ストアの既定は無期限。**ストアを消してもファイルは残る**ので `files.delete` を別に行う(probe は最後に削除する)。
- 詳細: [03 NOTES](../probes/03-file-search/NOTES.md)

### 6.4 04 Web search ツール

- **確かめること**: ツール型名、`web_search_call` の中身(外に出た検索クエリ)、引用の形、`tool_choice` 強制。
- **コマンド**: `uv run python probes/04-web-search/probe.py`(**DPA 対象外・別課金。4 リクエストのみ**)
- **出力で見る所**: A で `type='web_search' -> 受理` / B の `action.queries`(モデルが組み立てた実クエリ)/ C の `url_citation` / D で挨拶だけでも `output types=['web_search_call', 'message']`。
- **主要な発見**: 接続リソース不要でツール指定だけで動く。`action.queries` が「コンプライアンス境界外へ出た文字列」の実体。`tool_choice` 強制は無駄な検索と課金を生む。
- 詳細: [04 NOTES](../probes/04-web-search/NOTES.md)

### 6.5 05 Model router

- **確かめること**: japaneast での動作、難易度別のルーティング先、usage の見え方、`temperature` の受理。
- **コマンド**: `uv run python probes/05-model-router/probe.py`(要 `deployRouter=true`)
- **出力で見る所**: B/C の各行 `-> model=<実モデル名>`(2026-08-04 は 5 件中 4 件が `grok-4-1-fast-reasoning`、挨拶のみ `gpt-5-mini-2025-08-07`)/ D の `reasoning_tokens` / E が `temperature=0.2 -> OK`。
- **主要な発見**: 絞り込みなしのルーターは既定で非 OpenAI モデル(Grok)に流れる。`response.model` で監査可能。**データガバナンス要件がある案件では model subset 設定が必須**。現行ドキュメントでは非 OpenAI ルーティングの preview 表記が消え、正式仕様の挙動になっている。
- 詳細: [05 NOTES](../probes/05-model-router/NOTES.md)

### 6.6 06 Structured outputs(json_schema)

- **確かめること**: Responses `text.format`(strict)と Chat Completions `response_format` の両面、enum 矯正、`additionalProperties` 省略時の扱い。
- **コマンド**: `uv run python probes/06-structured-outputs/probe.py`
- **出力で見る所**: A の `パース成功。currency=JPY 明細数=2` / B の `currency=JPY ... 余計なキー=set()` / C が JSON 文字列 / D が 400 にならず JSON を返す。
- **主要な発見**: 両 API 面で strict が効き、プロンプトで指示しても schema が勝つ。Foundry は `additionalProperties` 省略の strict スキーマも受理(OpenAI 本家より緩い → 本家へ戻すと落ちうる)。
- 詳細: [06 NOTES](../probes/06-structured-outputs/NOTES.md)

### 6.7 07 Guardrails / コンテンツフィルター

- **確かめること**: 既定ポリシー下の注釈(`content_filter_results` / `prompt_filter_results`)、有害依頼と jailbreak 入力の扱い。
- **コマンド**: `uv run python probes/07-guardrails/probe.py`。D は手動: `az cognitiveservices account deployment show -n aif-fprobes -g rg-foundry-probes --deployment-name gpt-5.4-mini --query properties.raiPolicyName -o tsv`(期待: `Microsoft.DefaultV2`)
- **出力で見る所**: A にカテゴリ別 `severity` と入力側 `jailbreak`/ B は「ブロックされず応答が返った」(モデルの refusal)/ C が `BadRequestError ... 400`(content_filter)。
- **主要な発見**: 防御は 2 レイヤ — jailbreak は Prompt Shields が入力段で 400、素朴な有害依頼はモデル refusal(200)。アプリは両方を安全側の結果として扱う。
- 詳細: [07 NOTES](../probes/07-guardrails/NOTES.md)

### 6.8 08 埋め込みのエンドポイントルーティング

- **確かめること**: embeddings がアカウント / プロジェクトのどちらのエンドポイントで使えるか。
- **コマンド**: `uv run python probes/08-embeddings-routing/probe.py`(要 text-embedding-3-small デプロイ)
- **出力で見る所**: A が `"dims": 1536` で成功 / B が `NotFoundError 404`(`base_url=.../api/projects/probes/openai/v1/`)/ C が成功。
- **主要な発見**: **embeddings はプロジェクト経由 404・アカウント経由のみ成功**(chat/responses は両方 OK)。接続情報はプロジェクトとアカウントの 2 本を持つ。
- 詳細: [08 NOTES](../probes/08-embeddings-routing/NOTES.md)

### 6.9 09 継続評価(evaluation_rules)

- **確かめること**: prompt agent に `RESPONSE_COMPLETED` 駆動の継続評価ルールを掛け、自動評価ランが発火・観測できるか。
- **コマンド**: `uv run python probes/09-continuous-eval/probe.py`(最大 300 秒ポーリング)
- **出力で見る所**: A の `eval_...` / B のルール(`action.type=continuousEvaluation`・`filter.agentName`)/ C の一覧(`event=None` になる表現揺れがある)/ D の `自動ラン検出: continuousevalrun_... status=...` と `report_url`。
- **主要な発見**: ルールは **prompt agent スコープ必須**(filter なしは `Filter.AgentName is required`)。2026-08-04 は自動ランが `evals.runs.list` に出なかったが、eval のデータソースが公式の継続評価の形(`azure_ai_source` / `scenario: responses`)と違っていたため、2026-09-29 に probe を修正した。**修正後は未実測** — 再実測で D にランが出れば NOTES の「つまりどころ」を訂正する。
- 詳細: [09 NOTES](../probes/09-continuous-eval/NOTES.md)

## 7. 確認観点

| 確認 | # | 観点 | 確認方法 | 期待結果 |
| --- | --- | --- | --- | --- |
| [ ] | 1 | 正常系: 全 probe の完走 | `./run_all.sh` 後に `grep -c '^== ' logs/*.log` | 9 本すべてにログがあり、各 probe の観点見出しが最後(01 は I、09 は E)まで出ている |
| [ ] | 2 | 想定どおりのエラー(分岐・異常系) | `grep -n '^!!' logs/*.log` | 01 A の 404(アカウント直下)・01 H の 400・02 G の 400 のように、NOTES が「つまりどころ」として記録したものだけが出る。それ以外の `!!`(401/403 等)は §10 へ |
| [ ] | 3 | エンドポイント非対称(08・01) | `logs/08-embeddings-routing.log` の B、`logs/01-conversations.log` の A | どちらも 404。変わっていたら survey 08 / 03 の記述更新候補 |
| [ ] | 4 | データガバナンス(05) | `grep 'model=' logs/05-model-router.log` | ルーティング先のモデル名が出る。OpenAI 以外(grok 等)が混ざるなら、その環境で router を使う前に subset 設定が要る |
| [ ] | 5 | 外部送信の実体(04) | `logs/04-web-search.log` の `action.queries` | ユーザー入力由来の検索クエリ文字列が見える(= Bing に出た文字列) |
| [ ] | 6 | 継続評価の再実測(09) | `logs/09-continuous-eval.log` の D | `自動ラン検出: continuousevalrun_...` と `report_url` が出れば 2026-09-29 の修正で解消。出なければポータルの Monitor → Recurring evaluations を確認し NOTES に記録 |
| [ ] | 7 | 観測: 継続評価の結果の見え先 | ポータル Build → Evaluations(または Monitor タブ)/ D の `report_url` | probe-ce-agent の応答に対する coherence 評価が表示される |
| [ ] | 8 | 後片付け(probe 内) | 各 probe の最後の観点(02 H・03 G・09 E) | エージェント・ベクトルストア・ファイル・ルール・eval の削除が `OK` / `files.delete 済み` |
| [ ] | 9 | コスト・後片付け(基盤) | `az group show -n rg-foundry-probes` | 検証後は §9 で削除し、`ResourceGroupNotFound` になる |

## 8. トレース・評価の確認

probe はトレース(OpenTelemetry)を送らない(観察はすべて標準出力と `logs/`)。Application Insights は 09 の継続評価の結果と、必要時の手動確認のために接続してある。

```bash
az monitor app-insights query --app appi-fprobes -g rg-foundry-probes \
  --analytics-query "union traces, customEvents, dependencies | where timestamp > ago(1h) | summarize count() by itemType, name | top 20 by count_"
```

- 09 の評価結果の一次確認は `evals.runs.list` の `report_url`(ポータルの評価レポート)。App Insights 側に何が出るかは未実測。

## 9. 片付け

```bash
az group delete -n rg-foundry-probes --yes --no-wait   # ステートレス設計。router / Web search は従量なので放置しない
```

- probe が途中で落ちた場合は、残骸(`probe-prompt-agent` / `probe-ce-agent`・ベクトルストア `probe-store*`・`assistant-` ファイル・ルール `probe-continuous-rule`)が残り得る。RG ごと削除すればまとめて消える。

## 10. トラブルシューティング

| 症状 | 原因 | 対処 |
| --- | --- | --- |
| `ConfigError: FOUNDRY_PROJECT_ENDPOINT / ... を .env に設定` | `.env` 未作成・未記入 | `.env.example` をコピーして main.bicep の出力を転記 |
| `DefaultAzureCredential failed to retrieve a token` | `az login` していない / テナント違い | `az login`(必要なら `--tenant`) |
| 401 / 403 `PermissionDenied` | RBAC 伝播待ち、または roles.bicep 未実行 | 5〜15 分待つ / §5.1 の第 2 段を実行 |
| 01 A・08 B の 404 | 仕様(アカウント直下に Conversations なし・プロジェクト経由に embeddings なし) | 正常。NOTES の発見どおり |
| 02 G の 400 `Not allowed when agent is specified` | 仕様(エージェント指定時は `instructions` 上書き不可) | 正常 |
| `extra_body={"agent": ...}` で 400 | 旧名称 | `agent_reference` を使う |
| 05 で `DeploymentNotFound` | `deployRouter=true` でデプロイしていない | main.bicep を `deployRouter=true routerVersion=2025-11-18` で再デプロイ |
| 08 A も失敗 | text-embedding-3-small 未デプロイ | §5.1 の `deployment create` |
| 09 B で 403 `preview_feature_required` | 継続評価(プレビュー)に opt-in ヘッダーが必要になった | `AIProjectClient(..., allow_preview=True)` にする(SDK が `Foundry-Features: Evaluations=V1Preview` を付ける) |
| 09 D で自動ランが出ない | 非同期遅延・プロジェクト MI のロール不足・App Insights 未接続 | roles.bicep の実行を確認し、ポータルの Monitor で確認。NOTES 09 の 2026-09-29 追記を参照 |
| `RequestConflict`(デプロイ時) | アカウント配下のサブリソースを並行作成 | main.bicep は直列化済み。手動追加(埋め込み)は前のデプロイ完了後に |

## 11. 関連・更新履歴

- 一覧・検証対象外の理由・最新化チェック結果: [README](../README.md)
- 機能の GA/プレビュー状況: [features/03 Agent Service](../../../docs/survey/features/03-agent-service.md) / [features/04 ツール・ナレッジ](../../../docs/survey/features/04-tools-knowledge.md) / [features/02 モデル](../../../docs/survey/features/02-models.md) / [features/05 観測・評価](../../../docs/survey/features/05-observability-evaluation.md) / [features/06 安全性](../../../docs/survey/features/06-safety-guardrails.md) / [features/08 開発者サーフェス](../../../docs/survey/features/08-developer-experience.md)
- ユースケース実装例: [labs/maf-ports](../../maf-ports/README.md)

| 日付 | 内容 |
| --- | --- |
| 2026-09-29 | 初版(openai 2.53→3.20 / azure-ai-projects 2.4→2.7。09 の eval データソースを公式の継続評価の形に修正・要再実測) |
