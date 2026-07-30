# Microsoft Foundry Agent Service(ラボ用要約)

> corrective-rag ポートのサンプルコーパス。Microsoft Learn の Foundry Agent
> Service ドキュメントを学習用に要約したもの(2026-07 作成、ラボ内利用)。

## 概要

Foundry Agent Service は、Microsoft Foundry(旧 Azure AI Foundry)上で
エージェントをマネージドに実行するサービス。エージェントは「モデル+
instructions+ツール」の組で定義し、スレッド(会話履歴)・実行(run)・
ツール呼び出しのオーケストレーションをサービス側が担う。SDK(Python では
azure-ai-projects / azure-ai-agents)または REST で操作する。

## ツール

組み込みツールには次がある:

- **File Search**: アップロードしたファイルをサービス管理のベクトルストアに
  取り込み、エージェントが検索できるようにする(RAG のマネージド版)。
- **Code Interpreter**: サンドボックス内で Python を実行する。セッション
  単位の課金。
- **Web search / Bing Grounding**: Web の最新情報で回答をグラウンディング
  する。データ処理条項(DPA)の対象外で別課金となる点に注意が必要。
- **Azure AI Search ツール**: 既存の Azure AI Search インデックスを
  エージェントの知識ソースとして接続する。
- **MCP ツール**: Model Context Protocol サーバーへの接続(GA)。
- **OpenAPI / Function calling**: 任意の API・自作関数の呼び出し。

## Microsoft Agent Framework との関係

Microsoft Agent Framework(MAF)は Semantic Kernel と AutoGen を統合した
OSS フレームワークで、ChatAgent やグラフベースの Workflow をコードで
組み立てる。MAF のエージェントはローカル実行もできるし、Foundry の
モデルデプロイ(OpenAI v1 互換エンドポイント)を呼ぶこともできる。
Agent Service にホストさせる形(サーバー側エージェント)と、MAF で
クライアント側に組む形(本ラボの方式)は選択肢として使い分ける。

## 観測性

agent-framework は OpenTelemetry 計装を持ち、Application Insights に
接続すればエージェント実行・ツール呼び出し・モデル呼び出しのスパンが
Foundry ポータルの Traces に表示される。
