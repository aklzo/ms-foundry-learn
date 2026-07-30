# Foundry の観測性と評価(ラボ用要約)

> corrective-rag ポートのサンプルコーパス。Microsoft Learn の Foundry
> ドキュメントを学習用に要約したもの(2026-07 作成、ラボ内利用)。

## トレーシング

Foundry プロジェクトに Application Insights を接続すると、ポータルの
**Traces** でエージェント実行のスパンを確認できる。agent-framework は
OpenTelemetry の GenAI セマンティック規約に沿った計装を内蔵しており、
`configure_azure_monitor`(azure-monitor-opentelemetry)で接続文字列を
渡すだけで `invoke_agent` / `execute_tool` / `chat` などのスパンが送信
される。トークン使用量・モデル名・ツール引数もスパン属性に載る。

## 評価(Evaluation)

Foundry の評価機能は、データセット(JSONL)に対して**組み込み評価器**を
実行し、スコアをプロジェクトに記録する。代表的な評価器:

- **Groundedness(接地性)**: 回答が提供コンテキストに根拠を持つかを測る。
  RAG の品質評価の中心。コンテキスト・質問・回答の 3 つ組を入力する。
- **Relevance(関連性)**: 回答が質問に答えているか。
- **Retrieval**: 取得したコンテキスト自体が質問に関連しているか
  (リトリーバの品質)。
- **Task adherence / Intent resolution / Tool call accuracy**:
  エージェント的な挙動(指示遵守・意図解決・ツール呼び出しの正確さ)向け。
- **コンテンツ安全性系**: 暴力・自傷・憎悪など有害出力の検出。

評価は SDK(azure-ai-projects の evals API / azure-ai-evaluation)から
ローカルまたはクラウドで実行できる。CI に組み込んで回帰を検知する
「継続的評価」も推奨パターン。

## RAG 評価の実務

CRAG のような補正付き RAG では、(1) リトリーバの Retrieval スコア、
(2) 採点器(grader)の判定と実際の関連性の一致、(3) 最終回答の
Groundedness、を分けて測ると改善点が切り分けられる。groundedness は
「与えたコンテキストに対する接地」を測るため、Web 検索フォールバックを
通った回答では「何をコンテキストとして渡したか」を記録しておくことが
評価設計の前提になる。
