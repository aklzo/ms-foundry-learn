"""awesome-llm-apps rag_database_routing の MAF + Foundry 移植。

元アプリの三段カスケードルーティング(閾値検索 → LLM ルート → Web fallback)
のうち、前二段を Foundry IQ(Azure AI Search の agentic retrieval)の
knowledge base に委譲し、エージェントは MCP 経由(knowledge_base_retrieve)で
接続する。第三段の Web fallback は自前 DDG の関数ツール(設計判断は README)。
"""
