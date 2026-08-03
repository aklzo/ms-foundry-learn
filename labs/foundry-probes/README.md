# foundry-probes — Foundry 未検証機能の挙動確認ラボ

[maf-ports](../maf-ports/) の 13 ポートは Foundry のモデル推論・トレーシング・評価(バッチ)・Memory・Code Interpreter・MCP・Foundry IQ・hosted agent+Routines・Voice Live・AI Search を「ユースケースとして」検証済み。本ラボは **そこに乗らなかった機能を、単純例+観点別リクエストで叩いて挙動を記録する** 検証ラボ。

目的は動くアプリを作ることではなく、**各機能が実際にどう振る舞うか(発見メモ)と、どこで詰まるか(つまりどころ)を一次記録として残す**こと。各 probe は「観点ごとにリクエストを投げて生の応答を観察する」スクリプトで、実行ログ(`logs/`)がそのまま `NOTES.md` の根拠になる。

## probe 一覧(すべて 2026-08-04 ライブ実測)

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
| 09 | 継続評価(evaluation_rules) | 05 / プレビュー | **prompt agent スコープ必須(生 response 不可)**・配線は SDK 完結・自動ランは evals.runs に出ず Monitor 側集計 | [NOTES](./probes/09-continuous-eval/NOTES.md) |

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
4. **撤去**: `az group delete -n rg-foundry-probes`(ステートレス設計。model router / Web search は従量課金なので放置しない)。

## 注意

- **Web search(04)は DPA 対象外・データがコンプライアンス境界外へ出る**。probe は最小リクエストに絞ってある。
- **Model router(05)は既定で非 OpenAI モデル(Grok 等)に流れる**。データガバナンス要件のある環境で無設定デプロイしない。
- 実測は 2026-08-04・japaneast・gpt-5.4-mini v2026-03-17 時点。プレビュー機能は仕様変更があり得るので、NOTES の日付を見て再実測すること。

## 関連

- ユースケース実装例: [labs/maf-ports](../maf-ports/)(13 ポート。Memory / Code Interpreter / MCP / IQ / hosted / Voice など)
- 機能の可否判断: [docs/survey/features/](../../docs/survey/features/README.md)
