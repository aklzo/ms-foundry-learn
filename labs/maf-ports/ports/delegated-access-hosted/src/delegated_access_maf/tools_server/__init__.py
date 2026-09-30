"""MCP ツールサーバー(社内文書検索・取引先マスタ)と、最終判定点の 2 方式(server / apim)。

- ``app.create_app``: 3 つの FastMCP サーバーを契約パスに mount(ステートレス Streamable HTTP + JSON)
- ``auth``: エンドポイントごとの JWT 検証と認可(方式 B)、検証済み Principal の受け渡し
- ``docs_search``: AI Search のセキュリティフィルターによる文書の権限絞り込み
- ``suppliers``: 取引先マスタ(参照・支払条件の更新・監査記録)
- ``apim_emulator``: infra/apim/policies/*.xml を読んで方式 A を再現するオフライン用ゲートウェイ
- ``offline``: FakeEntra でプロセス内に立ち上げるテスト用ハーネス
- ``main``: uvicorn の起動口(``python -m delegated_access_maf.tools_server.main``)
"""
