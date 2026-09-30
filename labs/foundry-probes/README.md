# foundry-probes — Foundry 未検証機能の挙動確認ラボ

[maf-ports](../maf-ports/) の 13 ポートは Foundry のモデル推論・トレーシング・評価(バッチ)・Memory・Code Interpreter・MCP・Foundry IQ・hosted agent+Routines・Voice Live・AI Search を「ユースケースとして」検証済み。本ラボは **そこに乗らなかった機能を、単純例+観点別リクエストで叩いて挙動を記録する** 検証ラボ。

目的は動くアプリを作ることではなく、**各機能が実際にどう振る舞うか(発見メモ)と、どこで詰まるか(つまりどころ)を一次記録として残す**こと。各 probe は「観点ごとにリクエストを投げて生の応答を観察する」スクリプトで、実行ログ(`logs/`)がそのまま `NOTES.md` の根拠になる。

## probe 一覧(01〜09 は 2026-08-04、10 は 2026-09-30 ライブ実測)

| # | 機能 | サーベイでの位置 | 主な発見 / つまりどころ | NOTES |
| --- | --- | --- | --- | --- |
| 01 | Conversations API(サービス側会話状態) | 03 / GA | プロジェクト経由のみ(アカウントは 404)・TTL フィールド無し・store=False は会話にも残らない・model-router で別モデル継続可 | [NOTES](./probes/01-conversations/NOTES.md) |
| 02 | Prompt agents(サービス側定義+版) | 03 / GA | 版が自動採番・agent ごとに Entra ID 発行・`agent_reference` で旧版固定呼び出し・`instructions` 上書きは 400 | [NOTES](./probes/02-prompt-agents/NOTES.md) |
| 03 | File Search + ベクトルストア | 04 / GA | 埋め込みモデルの自前デプロイ不要・チャンク既定 800/400 実測一致・store 削除でファイルは残る・明示 TTL 可 | [NOTES](./probes/03-file-search/NOTES.md) |
| 04 | Web search ツール | 04 / GA | 型名は `web_search`・`action.queries` に実クエリ露出(DPA 対象外送信の実体)・tool_choice 強制で無駄検索も走る | [NOTES](./probes/04-web-search/NOTES.md) |
| 05 | Model router | 02 / GA | **japaneast で動く(survey のリージョン表が古い)**・既定でいきなり Grok にルーティング(データガバナンス注意)・response.model で監査可 | [NOTES](./probes/05-model-router/NOTES.md) |
| 06 | Structured outputs / json_schema | **未収録** | Responses/Chat 両面で strict 動作・enum 矯正が効く・`additionalProperties` 省略でも通る(本家より緩い) | [NOTES](./probes/06-structured-outputs/NOTES.md) |
| 07 | Guardrails / コンテンツフィルター | 06 / モデル=GA | 既定 `Microsoft.DefaultV2`・jailbreak は入力段 400・素朴な有害依頼はモデル refusal 任せ(2 レイヤ) | [NOTES](./probes/07-guardrails/NOTES.md) |
| 08 | 埋め込みのエンドポイントルーティング | 08 の注記 | **embeddings はプロジェクト経由 404 / アカウント経由のみ成功**(chat は両方 OK)。接続情報 2 本持ちが必須 | [NOTES](./probes/08-embeddings-routing/NOTES.md) |
| 09 | 継続評価(evaluation_rules) | 05 / プレビュー | **prompt agent スコープ必須(生 response 不可)**・配線は SDK 完結・自動ランは evals.runs に出ず Monitor 側集計(※2026-09-29: eval のデータソースが公式の継続評価の形と違っていたため probe を修正。**要再実測**) | [NOTES](./probes/09-continuous-eval/NOTES.md) |
| 10 | hosted agent の版更新と会話の継続 | arch 09 §6.3 / hosted agent GA | **会話は版をまたいで続く**(履歴はエージェント単位)・起動中のセッションは旧版のまま、**休止明けに現行の版で再開**(版の明示固定も休止明けは効かない)・ロールバックも同じ・旧版の削除はセッションが残ると 409 → `force=true` で履歴もファイルも残して現行版へ | [NOTES](./probes/10-hosted-version-continuity/NOTES.md) |

## 検証対象外(理由つき — 今後の候補)

「今は試さないが、理由と入口だけ残す」もの。将来コスト/権限が許せば同じ枠組みで追加する。

| 機能 | 状態 | 見送り理由 | 入口 |
| --- | --- | --- | --- |
| A2A(agent-to-agent) | プレビュー | ポータル未対応・agent card は REST のみ・2 エンドポイント構成で単純例が重い | survey 03、`az rest` + JSONRPC v1.0 |
| Image generation | プレビュー/一部 GA | `gpt-image-1*` は**限定アクセス(要申請)**、`gpt-image-2` のみ申請不要 | survey 02/04。申請後に probe 追加可 |
| AI Red Teaming Agent | GA | **評価専用の別リージョンプロジェクトが要る**+プロンプトが国外評価に渡る(法務確認前提)・多数の敵対的呼び出しで高コスト | survey 05、`beta.red_teams` |
| BYO storage / standard setup | GA相当 | Cosmos DB **最低 5,000 RU/s 常時課金**・トポロジ検証でありコスト対効果が薄い | survey 03/11、`capabilityHosts`(preview API) |
| Deep Research | **非推奨** | 死んだ classic 面。後継は `o3-deep-research`+web search(DPA 制約は 04 と同じ) | — |
| Browser automation / Computer use | プレビュー/限定 | Playwright Workspaces 別課金 / Computer use は登録申請制で叩けない | survey 04 |
| Global Batch / Prompt caching | GA | 低優先。probe 可能なので次サイクル候補(50% 割引・`completion_window` 固定など挙動確認価値あり) | survey 02、arch 09 |

> **リソース状態:** 検証用の基盤(RG `rg-foundry-probes`)は 2026-08-04 の実測完了後に**削除済み**(コスト停止)。再実行は下記手順で新規デプロイする。NOTES と `logs/`(ローカル)が一次記録として残る。
>
> **probe 10 は専用の最小基盤**(`probes/10-hosted-version-continuity/infra.bicep` = Foundry アカウント+プロジェクト+実行者の Foundry User。モデル・App Insights なし)で実測し、2026-09-30 に RG `rg-foundry-probes-p10` ごと削除・アカウントを purge 済み。main.bicep の基盤でも実行できる(Foundry User の割り当て込み)。

## 実行の前提

1. **基盤デプロイ(課金発生。検証後は RG ごと削除推奨)**
   ```bash
   az group create -n rg-foundry-probes -l japaneast
   az deployment group create -g rg-foundry-probes -f infra/main.bicep \
     -p baseName=fprobes modelName=gpt-5.4-mini modelVersion=2026-03-17 \
        userObjectId=$(az ad signed-in-user show --query id -o tsv) \
        deployRouter=true routerVersion=2025-11-18
   # MI ロール(第2段。principalId ローテーション対策で分離。理由は maf-ports/infra/shared.bicep)
   PID=$(az rest --method get --url "https://management.azure.com$(az cognitiveservices account show -n aif-fprobes -g rg-foundry-probes --query id -o tsv)/projects/probes?api-version=2025-06-01" --query identity.principalId -o tsv)
   AID=$(az cognitiveservices account show -n aif-fprobes -g rg-foundry-probes --query identity.principalId -o tsv)
   az deployment group create -g rg-foundry-probes -f infra/roles.bicep -p baseName=fprobes accountPrincipalId=$AID projectPrincipalId=$PID
   # 埋め込み probe 用(08)
   az cognitiveservices account deployment create -n aif-fprobes -g rg-foundry-probes \
     --deployment-name text-embedding-3-small --model-name text-embedding-3-small --model-version 1 \
     --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10
   ```
2. **`.env` 作成**(`main.bicep` の出力を転記。雛形 `.env.example`)。認証は `az login` 済みの Entra ID を既定とする。
3. **probe 実行**: `uv sync` → `uv run python probes/<NN>-<name>/probe.py`(結果は `logs/` に保存して NOTES の根拠にする)。`./run_all.sh` で全 probe を一括実行。

   詳細な実行手順と確認観点は [docs/runbook.md](./docs/runbook.md)(人間用 HTML: `docs/runbook.html`)。
4. **撤去**: `az group delete -n rg-foundry-probes`(ステートレス設計。model router / Web search は従量課金なので放置しない)。

## 注意

- **Web search(04)は DPA 対象外・データがコンプライアンス境界外へ出る**。probe は最小リクエストに絞ってある。
- **Model router(05)は既定で非 OpenAI モデル(Grok 等)に流れる**。データガバナンス要件のある環境で無設定デプロイしない。
- 実測は 2026-08-04・japaneast・gpt-5.4-mini v2026-03-17 時点。プレビュー機能は仕様変更があり得るので、NOTES の日付を見て再実測すること。

## 検証結果(2026-09-29 最新化チェック)

Azure リソースは削除済みのため**オフライン(静的)確認のみ・ライブ未検証**。probe はライブ専用スクリプトなので、全 9 本を `py_compile`・`ruff check` し、呼び出している SDK メソッドとキーワード引数を installed SDK(openai 3.20.0 / azure-ai-projects 2.7.0)のシグネチャと AST で突き合わせた(不一致 0)。

- **依存更新**: openai 2.53.0 → **3.20.0**、azure-ai-projects 2.4.0 → **2.7.0**、azure-identity 1.25.3(据え置き)、ruff 0.16.9。pyproject の下限を検証版に引き上げ、未使用だった `httpx` 依存を削除(openai 3.x は HTTP クライアントが httpx2 に変わり、azure-ai-projects 2.5.0 以降も追随。probe は httpx を直接使わない)。`uv.lock` は従来どおり git 管理外(`.gitignore`)。
- **改修(09 継続評価)**: eval 定義を公式の継続評価の形 `data_source_config={"type": "azure_ai_source", "scenario": "responses"}`(data_mapping なし)に変更し、ラン検出のポーリングを 300 秒・`report_url` 表示に拡張。旧版はバッチ評価用の `custom` + `data_mapping` で作っており、公式手順(ランは `evals.runs.list` に `continuousevalrun_*` として現れる)と食い違っていた → NOTES の「evals.runs に出ない」は**要再実測**。出典: https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard (2026-09-03 版)
- **変更不要(01〜08)**: Conversations / Responses / Files / Vector stores / Chat Completions / Embeddings / Evals の呼び出しは openai 3.20.0 でシグネチャ・戻り値フィールド(`output_text`・`content_filter_results` 等の拡張フィールド含む)とも互換。02 の `get_openai_client(agent_name=...)` は 2.7.0 でも同じエージェントエンドポイントを向き、公式クイックスタート(2026-09-03 版)の主経路と一致。
- **現行ドキュメントとの差分(挙動の再解釈が要るもの)**: 05 — Model router ページから「非 OpenAI ルーティングはプレビュー」の表記が消え、既定で Grok 等に流れる挙動は正式仕様側になった(2025-11-18 版は 2027-05-20 リタイア予定)。04 — Responses の `web_search_preview` は「サポートされるが非推奨」、prompt agent 用 `WebSearchTool` には `external_web_access`(SDK 2.6.0+)が追加。
- **Bicep**: `az bicep build` で main / roles とも警告なし。`Microsoft.CognitiveServices/accounts@2025-06-01` は他ラボと同じ GA API のため据え置き。RBAC ロール名は「Foundry User(旧 Azure AI User)」の改名をコメントに反映済み(ロール ID は不変)。
- **今後の選択肢**: 02 の版固定は `agent_reference.version` に加え、エージェントエンドポイントの `version_selector` でピン留めする方法が公式化(configure-agent 2026-09-11 版)。

## 関連

- ユースケース実装例: [labs/maf-ports](../maf-ports/)(13 ポート。Memory / Code Interpreter / MCP / IQ / hosted / Voice など)
- 機能の可否判断: [docs/survey/features/](../../docs/survey/features/README.md)
