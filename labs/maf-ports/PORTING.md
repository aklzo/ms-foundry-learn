# 移植規約(awesome-llm-apps → MAF + Foundry)

各エージェントの移植はこの規約に従う。目的は「動くものを作る」だけでなく、**MAF と Foundry の境界(何が楽になり、何が難しいか)を記録する**こと。

## 1. ディレクトリ規約

```
labs/maf-ports/
├── README.md            # ラボ概要・進捗表
├── PORTING.md           # 本ファイル(移植規約)
├── INVENTORY.md         # 元リポジトリ 156 プロジェクトの棚卸しと優先順位
├── infra/
│   └── shared.bicep     # 共有基盤(Foundry リソース+プロジェクト+モデル+App Insights)
└── ports/<agent-name>/
    ├── README.md        # 元アプリ / 設計判断 / 元との差分 / 学び(MAF vs 元FW)
    ├── pyproject.toml   # uv + hatchling(agentic-search-maf と同一規約)
    ├── src/<pkg>/
    ├── tests/           # オフラインテスト(必須)+ ライブスモーク(env ゲート)
    └── infra/main.bicep # エージェント固有リソース(共有基盤を参照)
```

## 2. フレームワーク対応表(元 → MAF/Foundry)

| 元の構成要素 | 移植先 | 備考 |
| --- | --- | --- |
| agno / openai-agents / langchain の Agent | MAF `ChatAgent`(agent-framework-core) | ツールは `@ai_function` 相当へ |
| マルチエージェント協調(sequential / hierarchical) | MAF Workflows(グラフ) | agentic-search-maf の実装パターンを流用 |
| DuckDuckGo / SerpAPI / Exa 検索 | Foundry **Web search ツール**(GA)or httpx 自前 | Web search は DPA 対象外・別課金に留意 |
| コード実行(e2b 等) | Foundry **Code Interpreter**(GA・セッション課金) | オフラインテストではフェイク |
| mem0 / 自前メモリ | Foundry **Memory**(プレビュー) | プレビュー依存は README に明記 |
| ベクトルDB(Qdrant/Chroma/LanceDB…) | **Azure AI Search**(または File Search) | インデックス構築は infra/ + スクリプト |
| MCP サーバー接続 | MAF の MCP クライアント or Foundry MCP ツール(GA) | |
| Streamlit UI | **CLI 化**(初回移植では UI を作らない) | UI は学習目的外。必要になれば後付け |
| OpenAI API 直 | Foundry プロジェクトエンドポイント + `agent-framework-openai` | Entra ID 認証(キーレス) |

## 3. 観測性・評価(全ポート必須)

- **トレーシング**: agent-framework の OpenTelemetry 計装を有効化し、共有基盤の Application Insights へ送信。接続文字列は env `APPLICATIONINSIGHTS_CONNECTION_STRING`。ポータルの Traces で確認できることをライブスモークの確認項目に含める。
- **評価**: 各ポートに `tests/eval_dataset.jsonl`(5〜10 ケース)を用意し、
  - オフライン: 期待挙動のアサーション(ツール呼び出し順・出力構造)
  - ライブ(任意): `azure-ai-projects` の evals API で組み込み評価器(relevance / task adherence 等)を1回流す手順を README に記載
- 評価は「回して見る」こと自体が学習目的。スコアの合否ラインは設けない。

## 4. テスト規約

- **オフラインテスト(必須・CI 相当)**: LLM・検索・外部 API はすべて scripted fake(agentic-search-maf の `ScriptedAgent` パターン)。`uv run pytest` がネットワークなしで通ること。
- **ライブスモーク(必須・手動)**: `FOUNDRY_PROJECT_ENDPOINT` 等の env が揃っているときだけ実行(`pytest -m live`)。実モデルで 1 シナリオ流し、(1) 正常応答 (2) トレースがポータルに出る、を確認。
- 完了条件: オフライン緑 + ライブスモーク 1 回成功 + トレース確認。

## 5. Bicep 規約

- 共有基盤(`infra/shared.bicep`)は 1 回だけデプロイ: Foundry リソース(kind `AIServices`)+ default プロジェクト + モデルデプロイ(Global Standard・最小容量)+ Log Analytics + App Insights。
- 各ポートの `infra/main.bicep` は**エージェント固有リソースのみ**(AI Search、Storage 等)。共有基盤の名前を param で受けて `existing` 参照。固有リソースが無いポートは main.bicep に「共有基盤のみで動く」ことをコメントで明記(空でも作る=規約の一貫性優先)。
- 検証: `az bicep build` をコミット前に必ず通す。実デプロイは `az deployment group create`。
- **コスト注意**: モデルは最小容量・従量。AI Search は Basic。使わない期間はリソースグループごと削除できる設計(ステートレス)を守る。

## 6. 進め方(1 ポート = 1 サイクル)

1. 元コードを読み、README に「元の構成」を 5 行で要約
2. MAF で実装(CLI)+ オフラインテスト
3. Bicep(固有分)+ `az bicep build`
4. ライブスモーク(共有基盤にデプロイ・実行・トレース確認)
5. README に「学び: MAF で楽だった点 / 苦しかった点 / 元 FW との差」を必ず 3 点以上書く ← **ここが本ラボの成果物**
6. コミット(1 ポート 1 コミット)

## 7. 移植しないもの(明示的スコープ外)

- Streamlit / Next.js の UI 再現
- ローカル LLM(Ollama)前提の構成(Foundry 移植の学習価値が薄い)→ モデルだけ Foundry に差し替えて本質を移植
- ファインチューニングチュートリアル(コスト・時間対効果が合わない)
