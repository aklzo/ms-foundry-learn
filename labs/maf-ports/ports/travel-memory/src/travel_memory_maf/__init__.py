"""ai_travel_agent_memory(OpenAI + mem0 + Qdrant + Streamlit)の
MAF + Microsoft Foundry 移植。

元: ~/oss/awesome-llm-apps/advanced_llm_apps/llm_apps_with_memory_tutorials/ai_travel_agent_memory

長期記憶付き旅行相談チャット — 毎ターン「記憶検索 → コンテキスト注入 →
応答生成 → 会話を記憶へ追加」— の記憶層を、mem0(ローカル Qdrant)から
Foundry Agent Service の **Memory(パブリックプレビュー)** へ 1:1 置換する。
mem0 の user_id は Foundry Memory の scope に対応。設計判断は README 参照。
"""

__version__ = "0.1.0"
