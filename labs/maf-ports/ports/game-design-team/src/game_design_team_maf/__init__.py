"""ai_game_design_agent_team(AutoGen/AG2 旧 Swarm API + Streamlit)の
MAF + Microsoft Foundry 移植。

元: ~/oss/awesome-llm-apps/advanced_ai_agents/multi_agent_apps/agent_teams/ai_game_design_agent_team

元アプリの核心である AG2 Swarm の協調 — AfterWork のハンドオフ・リング+
共有 context_variables + UPDATE_SYSTEM_MESSAGE の動的プロンプト — を、
MAF core では「4 役割 Executor の明示的なリング(ループエッジ)+
GameDesignContext をメッセージとして運ぶ+context から毎回プロンプトを
組み立てる」で表現する。対応表と表現力差の考察は README を参照。
"""

__version__ = "0.1.0"
