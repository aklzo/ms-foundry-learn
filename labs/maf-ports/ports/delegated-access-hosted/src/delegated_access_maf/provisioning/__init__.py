"""デプロイ・セットアップの純関数部(scripts/ から使う)。hosted agent の zip には入れない。

- ``entra``: アプリ登録 2 つ・管理者同意・アプリロール割り当て・Foundry 側のロール
  (scripts/setup_entra.py。既定は dry-run で、実行する Graph / ARM 呼び出しを全部表示する)
- ``hosted_agent``: hosted agent のコード zip と定義(scripts/deploy_hosted_agent.py)
"""
