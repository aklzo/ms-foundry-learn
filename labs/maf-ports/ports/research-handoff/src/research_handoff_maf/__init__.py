"""openai_research_agent(OpenAI Agents SDK + Streamlit)の
MAF + Microsoft Foundry 移植。

元: ~/oss/awesome-llm-apps/starter_ai_agents/openai_research_agent

元アプリの核心である handoff(triage → research / editor への制御移譲)を、
MAF ではトリアージの構造化出力(ルーティング判断)+ switch-case エッジで
表現する。判断の経緯は README の「MAF の handoff サポート調査」を参照。
"""

__version__ = "0.1.0"
