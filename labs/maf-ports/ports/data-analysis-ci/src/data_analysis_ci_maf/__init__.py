"""ai_data_analysis_agent(Agno + DuckDB/Pandas ツール + Streamlit)の
MAF + Microsoft Foundry 移植。

元: ~/oss/awesome-llm-apps/starter_ai_agents/ai_data_analysis_agent

CSV/Excel を自然言語で分析する単一エージェント。コード実行の所在を
「ローカルプロセス内の DuckDB/Pandas」から **Code Interpreter
(サーバー側サンドボックス。OpenAI v1 Responses API の code_interpreter
コンテナツール)** へ置き換え、MAF の
``OpenAIChatClient.get_code_interpreter_tool()`` で消費する。設計判断は
README 参照。
"""

__version__ = "0.1.0"
