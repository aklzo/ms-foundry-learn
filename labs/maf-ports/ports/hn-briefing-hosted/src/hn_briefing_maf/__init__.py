"""hn-briefing-maf — 常時稼働 HN ブリーフィングエージェントの MAF + Foundry 移植。

二層構成:

- ロジック層: 収集(HN Algolia)→ 決定論ランキング → LLM ブリーフ生成の
  直列ワークフロー(CLI 実行・オフラインテスト可能)
- ホスティング層: 同じロジックを Foundry hosted agent(Responses protocol)
  として包む hosting/ 一式+Routines(プレビュー)の日次スケジュール起動
"""

__version__ = "0.1.0"
