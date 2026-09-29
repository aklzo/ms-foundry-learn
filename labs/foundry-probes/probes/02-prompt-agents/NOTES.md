# Prompt agents(サービス側エージェント定義)— 挙動発見メモ(2026-08-04 実測)

環境: gpt-5.4-mini / japaneast / azure-ai-projects 2.4.0

## 発見(挙動)

- **`create_version` は同名エージェントへの呼び出しごとに版が 1, 2, 3… と増える**(自動スナップショット)。戻り値 id は `name:version` 形式。`draft` / `status: active` フィールドあり。
- **エージェントごとに Entra ID が自動発行される。** 戻り値に `instance_identity.principal_id` と `blueprint_reference: ManagedAgentIdentityBlueprint` が入る。survey 03 の「agent identity」の実態。エージェント単位の RBAC(ツール接続先への最小権限)がここに効く。
- **呼び出しは 2 通り確認:**
  1. `project.get_openai_client(agent_name=...)` → `responses.create(input=...)`(model 指定不要。定義側の model が使われ、既定で最新版)
  2. 素の project openai client + `extra_body={"agent_reference": {"type": "agent_reference", "name": ..., "version": "1"}}` — **version 指定で旧版に固定呼び出しできる**(カナリア/ロールバックに使える)。省略時は最新版。
- **conversation と組み合わせると「定義も状態もサービス側」の最小構成が成立**(クライアントは input を送るだけ)。
- **function ツールはクライアント実行ループ。** 定義に `FunctionTool` を付けると `function_call` item がクライアントに返る(`agent_reference` に応答した版番号つき)。サービス側で完結するのは Foundry 管理ツール(File Search 等)だけ。
- 版の削除は有効版が他にあれば OK。エージェント削除で全版消える。

## つまりどころ

- **エージェント指定時は `instructions` パラメータ上書き不可**: 400 `invalid_payload: Not allowed when agent is specified`。ターン限定の指示は input 側に書くか、版を切るしかない。
- **`extra_body={"agent": ...}` は 400**: `The 'agent' property is deprecated. Use 'agent_reference' instead.` — 古いサンプルコードの写経に注意。
- `create_version` は upsert 的(存在しなければ作成、あれば新版)。「二重作成エラー」は出ないので、名前の typo が新エージェント作成に化ける。

## SI 判断メモ

- maf-ports(MAF)のようにクライアント側に定義を持つ構成と違い、prompt agent は**プロンプト改訂をデプロイなしで版管理**できる。定義変更の主体が非エンジニア(業務側)になる案件では prompt agent 優位。
- ただしツール実行を伴う業務ロジックはどのみちクライアント(または hosted agent)に残るので、「prompt agent = プロンプト+Foundry 管理ツールの範囲」で線を引くのが実務的。

## 2026-09-29 追記(最新化チェック・ライブ未検証)

- azure-ai-projects 2.7.0 / openai 3.20.0 で probe の呼び出しはすべてそのまま解決する(静的確認)。`get_openai_client(agent_name=...)` の向き先は 2.4 と同じ **エージェントエンドポイント** `{project}/agents/{name}/endpoint/protocols/openai`(`api-version=v1` と `Foundry-Features` ヘッダーを SDK が自動付与)。
- 公式クイックスタート(get-started-code 2026-09-03 版)もこの `get_openai_client(agent_name=...)` 経路を主経路にしている。configure-agent(2026-09-11 版)によると、エンドポイントはエージェント作成時点で有効・既定の版ルーティングは **Always use latest**(= D の「既定で最新版」と一致)。
- **今後の選択肢**: 版固定は `extra_body.agent_reference.version` のほか、エンドポイント側で `agents.update_details(agent_endpoint=AgentEndpointConfig(version_selector=VersionSelector([FixedRatioVersionSelectionRule(agent_version="2", traffic_percentage=100)])))` とピン留めする方法が公式化された(Teams / M365 公開時はこちらが前提)。呼び出し側の権限は **Foundry Agent Consumer**(以上)ロール。
- `FunctionTool` の `strict` は SDK の型上 2.4 から必須だが、省略しても 2026-08-04 は動作した。probe は実測時の要求を変えないため省略のまま。
