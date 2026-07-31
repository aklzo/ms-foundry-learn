"""governed-agent-maf: MAF middleware でガバナンス層(決定論ポリシー・信頼ゲート・
ハッシュ連鎖監査)を実装した経費精算エージェント。

元アプリ 2 本の統合移植:
- ai_agent_governance(ツール実行前の決定論ポリシー強制)
- trust_gated_agent_team(信頼スコアゲート+改ざん検知ハッシュ連鎖監査)
"""

__version__ = "0.1.0"
