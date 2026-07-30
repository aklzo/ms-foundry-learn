"""corrective_rag(LangChain + LangGraph + Qdrant + Tavily + Streamlit)の
MAF + Microsoft Foundry 移植。

元: ~/oss/awesome-llm-apps/rag_tutorials/corrective_rag

CRAG(Corrective RAG)の補正フロー — 検索 → 文書採点 → 〈関連なら生成 /
低関連ならクエリ書換 → Web 検索フォールバック → 生成〉 — を、LangGraph の
StateGraph から MAF WorkflowBuilder(switch-case エッジ)へ写像する。
ベクトルストアは Qdrant → Azure AI Search(Free SKU)に置換。設計判断は
README 参照。
"""

__version__ = "0.1.0"
