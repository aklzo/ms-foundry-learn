# 05. オブザーバビリティ・評価

[← 機能一覧 TOP](./README.md)

> **最終更新:** 2026-07-29(learn.microsoft.com 現行ページ確認)

## 概要

トレーシング・評価・モニタリングを統合した観測基盤を扱う。領域別のステータスは混在しており、[Feature readiness at GA](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability)(2026-07-22 更新)の記載が最も体系的:

- Tracing(Trace Replay 含む): **prompt / hosted エージェントは GA、workflow / 外部エージェントはプレビュー**
- Tracing VNet: プレビュー
- トレース→評価データセット変換: プレビュー
- Evaluations: **GA**(一部評価器・機能はプレビュー)
- Monitoring: **プレビュー**
- Red teaming: **GA**
- Operate > Compliance: プレビュー

## 機能一覧

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Observability(全体像) | トレース・モニタリング・評価を統合した AI アプリのライフサイクル観測基盤。App Insights 統合ダッシュボード | 領域別に混在(上記の Feature readiness 参照) | Foundry(新)中心 | 記載なし | 対応(`azure-ai-projects`) | https://learn.microsoft.com/en-us/azure/foundry/concepts/observability | エージェントプレイグラウンドの評価は全プロジェクトで既定有効・従量課金 |
| Tracing(トレーシング) | OpenTelemetry セマンティック規約ベースで App Insights にテレメトリ送信。サーバー側トレースはコード変更不要、ポータルで 90 日分閲覧可 | GA(prompt / hosted エージェント)。workflow・外部エージェントはプレビュー | Foundry(新)の Agents > Traces タブ | 記載なし | 対応(`azure-ai-projects` + opentelemetry-sdk + azure-core-tracing-opentelemetry) | https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-setup | LangChain / LangGraph / OpenAI Agents SDK / Microsoft Agent Framework 連携対応。VS Code Foundry Toolkit でローカルトレース可。Tracing の VNet 対応はプレビュー |
| Trace Replay | 会話トレースを Trajectories ビュー(スパン階層+ウォーターフォール)と User ビュー(チャット再現)で再生・分析 | 表記揺れあり: What's new(2026年6月)は「(preview)」、GA 一覧(2026-07-22)は Tracing に含めて「GA for prompt and hosted agents」→ **prompt / hosted は実質 GA、workflow / 外部はプレビュー**と読むのが最新記載に忠実 | Foundry(新)ポータルのみ(Traces ページから起動) | 記載なし | 記載なし(ポータル機能) | https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-replay | 再生には2スパン以上必要。Log Analytics Reader ロール必須 |
| トレース→評価データセット変換(Data Generation) | 本番トレースをインテリジェントサンプリング(MinHash による多様性抽出、低品質トラフィック除去)で評価/FT 用データセットに変換 | パブリックプレビュー(タイトルに「(preview)」明記) | Foundry(新)の Data Generation タブ | 記載なし | 対応(`azure-ai-projects`>=2.2.0、`project_client.beta.datasets`) | https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/traces-to-dataset | max_samples は 15〜1000。App Insights / ストレージへのパブリックネットワークアクセスが必要 |
| Evaluations(評価・クラウド評価) | Foundry プロジェクトに対する評価実行。エージェントターゲット評価、ルーブリック評価器の自動生成、データセット評価 | GA(「some evaluators and features are Preview」)。プレビュー部分: 会話レベル評価、トレース評価、会話シミュレーション、合成データ評価 | Foundry(新)の Evaluations タブ・評価ウィザード | 記載なし | 対応(`azure-ai-projects`>=2.2.0 + OpenAI evals クライアント。C# / REST もあり) | https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/cloud-evaluation ・ https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluate-agent | **Entra ID 認証必須(API キー不可)**。GitHub Actions 連携で CI/CD ゲート化可 |
| 組み込み評価器: 品質・RAG・類似度 | Coherence, Fluency, Retrieval, Groundedness, Relevance, BLEU/ROUGE 等 | 概ね GA。Groundedness Pro / Response Completeness のみプレビュー表記 | 対応 | 記載なし | 対応(`builtin.*` 名で指定) | https://learn.microsoft.com/en-us/azure/foundry/concepts/built-in-evaluators | Azure OpenAI graders(Model Labeler 等)にはプレビュー表記なし |
| 組み込み評価器: 安全性 | Hate/Unfairness, Sexual, Violence, Self-Harm, Protected Materials, Indirect Attack (XPIA), Code Vulnerability, Ungrounded Attributes, Prohibited Actions, Sensitive Data Leakage | GA相当(プレビュー表記なし) | 対応 | 記載なし | 対応 | https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/risk-safety-evaluators | AI 支援安全性評価器はリージョン制限あり。従量課金対象 |
| 組み込み評価器: エージェント向け | Intent Resolution, Task Adherence, Task Completion, Customer Satisfaction, Tool Call Accuracy, Tool Selection, Tool Input/Output 系, Task Navigation Efficiency, Quality Grader | Intent Resolution / Task Adherence / Task Completion / Customer Satisfaction / Quality Grader = プレビュー。Tool Call Accuracy / Tool Selection / Tool Input Accuracy / Tool Output Utilization / Tool Call Success / Task Navigation Efficiency = GA相当(プレビュー表記なし) | 対応 | 記載なし | 対応(evals API、`builtin.task_adherence` 等) | https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators | Bing Grounding / Azure AI Search / Code Interpreter 等のツール呼び出しを含む会話ではツール系評価器のサポートが限定的 |
| Rubric 評価器 / カスタム評価器 | エージェントのコンテキストから LLM ジャッジ用の重み付きルーブリックを自動生成。独自ロジックのカスタム評価器も定義可 | どちらもパブリックプレビュー(「(preview)」明記) | 対応 | 記載なし | 対応(`project_client.beta.evaluators`) | https://learn.microsoft.com/en-us/azure/foundry/concepts/built-in-evaluators | evaluate-agent ページでは Rubric 評価器をエージェント評価の主要手段として推奨 |
| ローカル評価(`azure-ai-evaluation`) | `evaluate()` API とローカル評価器クラス群によるローカル実行評価 | パッケージ自体は GA(stable 1.18.2、非推奨表記なし)。ただし**ドキュメントは Foundry (classic) 専用に移動**(「This article isn't available for the new Foundry portal」) | classic のみ(新ポータルのドキュメント体系から除外) | 記載なし | 対応(`pip install azure-ai-evaluation`) | https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/develop/evaluate-sdk ・ https://learn.microsoft.com/en-us/python/api/overview/azure/ai-evaluation-readme | 新 Foundry の評価は `azure-ai-projects`>=2.2.0 + OpenAI evals クライアントに全面移行。明示的な後継宣言・廃止日は未確認 |
| 継続的評価(Continuous evaluation) | 本番トラフィックのサンプリング評価。`EvaluationRule`(response_completed イベント、既定 100 回/時)で構成 | 要確認(Monitor 設定表では Continuous evaluation に preview 表記なし〈Scheduled evaluations / Red team scans / Alerts は preview 明記〉。一方 GA 一覧では Monitoring 領域全体がプレビュー) | Foundry(新)の Monitor タブ設定 | 記載なし | 対応(`azure-ai-projects`>=2.0.0 の `evaluation_rules`。.NET もあり) | https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard | カスタム評価器(プレビュー)も継続的評価に追加可。プロジェクトのマネージド ID に Foundry User ロール必須 |
| AI Red Teaming Agent | PyRIT ベースの自動敵対的スキャン。ローカル/クラウド実行、ASR (Attack Success Rate) を算出 | GA(GA 一覧に「Red teaming: GA」。概念ページにプレビューバナーなし) | 対応(結果を Foundry で記録・追跡) | 記載なし | 対応(`azure-ai-projects`>=2.0.0。REST は api-version `2025-11-15-preview`) | https://learn.microsoft.com/en-us/azure/foundry/concepts/ai-red-teaming-agent ・ https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/run-ai-red-teaming-cloud | エージェント固有リスク(Prohibited Actions / Sensitive Data Leakage / Task Adherence)はクラウドのみ。対応リージョン: East US 2, France Central, Sweden Central, Switzerland West, US North Central。workflow / 非 Foundry エージェント・Function ツールは非対応 |
| Agent Monitoring Dashboard | トークン使用量・レイテンシ・実行成功率・評価スコア・red teaming 結果の統合ダッシュボード | パブリックプレビュー(「View agent metrics (preview)」、GA 一覧「Monitoring: Preview」) | Foundry(新)の Build > エージェント > Monitor タブ | 記載なし | 継続的評価ルール設定のみ SDK(表示はポータル) | https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard | データは接続済み App Insights に保存(保持・課金は App Insights 設定に従う)。AI Gateway 経由で非 Foundry エージェントのオンボードも可 |
| Microsoft Purview 連携 | Foundry の AI インタラクションに対する DSPM for AI、監査、データ分類、秘密度ラベル、DLP、IRM、eDiscovery、保持ポリシー等 | 要確認(Purview 側ページにプレビュー表記なし。Foundry 側の有効化 UI〈Control Plane の Compliance〉は GA 一覧でプレビュー) | Foundry Control Plane で有効化、または Defender for Cloud 経由 | 記載なし | 記載なし(Purview API / Graph API 経由) | https://learn.microsoft.com/en-us/purview/ai-azure-foundry | Purview の従量課金有効化が必要。Entra ID ユーザーコンテキスト付き API 呼び出しがポリシー適用の条件 |
| Defender for Cloud(AI threat protection) | 生成 AI アプリ/エージェントへの脅威(ジェイルブレイク、データ漏えい、資格情報窃取等)をリアルタイム検知。Defender XDR 統合 | GA(「Release state: Generally available (GA)」明記) | Azure portal / Defender XDR ポータル | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/defender-for-cloud/ai-threat-protection | 30 日間無料試用。テキストトークンのみスキャン。Azure Government / 21Vianet 非対応 |

## 補足ノート

**1. Trace Replay のステータス揺れ(重要)**
What's new(June 2026)では「(preview)」として新規掲載、より新しい GA 一覧(2026-07-22 更新)では Tracing に含めて「GA for prompt and hosted agents」。個別記事タイトルに (preview) は付いていない。報告上は両出典を併記し、「prompt / hosted エージェントでは実質 GA 入り、workflow / 外部エージェントはプレビュー」と読むのが最新記載に忠実。

**2. 評価 SDK の世代交代**
新 Foundry の評価ドキュメントは全面的に **`azure-ai-projects`(>=2.2.0)+ OpenAI 互換 evals API**(`client.evals.create` / `builtin.*` 評価器名)ベースに書き換えられた。`azure-ai-evaluation`(ローカル評価)は stable 1.18.2 が存続し廃止告知はないが、ドキュメントは foundry-classic 配下(hub-based プロジェクト向け)に隔離された。正式な移行アナウンス文書は未確認。

**3. 継続的評価の位置づけ**
Monitor 設定パネルでは Continuous evaluation のみ preview 表記がなく、Scheduled evaluations / Red team scans / Alerts が preview 明記。ただしダッシュボード表示自体が preview であり、GA 一覧でも Monitoring 領域全体がプレビューのため、本番採用判断時は「周辺はプレビュー」として扱うのが安全。

**4. サーフェス全般の傾向**
観測性・評価領域の手順書はすべて「Foundry(新)ポータル + Python SDK(`azure-ai-projects`)」が主線で、一部 C#/.NET と REST(api-version `2025-11-15-preview`)を併記。**Azure CLI の手順はどのページにも記載なし**。
