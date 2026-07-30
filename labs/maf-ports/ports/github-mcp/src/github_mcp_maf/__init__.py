"""github_mcp_agent(agno + 公式 github-mcp-server Docker/stdio + Streamlit)の
MAF + Microsoft Foundry 移植。

元: ~/oss/awesome-llm-apps/mcp_ai_agents/github_mcp_agent

GitHub リポジトリを自然言語で照会する単一エージェント。MCP 接続を
「Docker で起動する stdio サーバー」から **GitHub 公式リモート MCP サーバー**
(https://api.githubcopilot.com/mcp/、PAT を Authorization: Bearer で送る)へ
置き換え、MAF の ``MCPStreamableHTTPTool`` で消費する。設計判断は README 参照。
"""

__version__ = "0.1.0"
