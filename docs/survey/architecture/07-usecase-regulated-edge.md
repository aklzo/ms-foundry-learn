# 07. ユースケース編 D — 規制業種・閉域・データ主権・エッジ

[← アーキテクチャ TOP](./README.md)

> **最終更新:** 2026-07-30(公式ドキュメントとの突合検証で訂正)

金融・公共・医療など、**ネットワーク分離とデータ所在を先に決めなければ設計が始まらない**類型。このページの内容は [03. 選定ガイド](./03-decision-guide.md) の G1(データ・規制ゲート)と G2(ネットワークゲート)の詳細版にあたる。

## この章で最初に伝えるべき 3 つの事実

1. **ネットワーク構成は Foundry アカウント作成時にしか決められない。**後付け不可、委任サブネットの変更も不可。変更したければ**再デプロイ**。「PoC は basic で始めて本番で standard + VNet に切り替える」という計画は**アカウント再作成を必須とする。**
2. **閉域を選ぶと使えなくなる Foundry 機能がかなりある。**特に **File Search・Traces・Memory・Logic Apps・Browser Automation・Computer Use・Image Generation** は非対応。設計は「使える機能の一覧」から始める。
3. **「日本国内処理」を保証できるのは `Standard`(リージョナル)または `ProvisionedManaged` だけ。****APAC Data Zone は日本以外(豪・韓・星・印)も含むため、多くの日本の規制要件では不十分。**

---

## 1. 最上位の分岐 — 3 つの egress モデル

Foundry のネットワーク設計は「**egress(送信)モデルを先に決める**」のが公式の意思決定順序。egress の選択が inbound の選択肢を決める。

| Egress モデル | Inbound の選択肢 | 適する場面 |
|---|---|---|
| **Public egress** | パブリック(IP 制限可)/ VNet 内 Private Endpoint | egress 分離なし。PE を付けても**呼び出し元制限だけ**でエージェントの送信は公開網 |
| **BYO Virtual Network**(サブネット注入) | VNet 内 Private Endpoint | 完全分離。IP レンジ・ピアリング・ルーティングを自社統制 |
| **Managed Virtual Network**(Microsoft 管理) | VNet 内 Private Endpoint | 完全分離だが IP 管理をしたくない / IP レンジが重複する場合 |

### BYO VNet と Managed VNet の公式比較

| 観点 | Managed network | Custom (BYO) network |
|---|---|---|
| メリット | Microsoft がサブネットレンジ・IP 選択・委任を処理 | **フルコントロール:** 自前 firewall、UDR、ピアリング、サブネット委任 |
| 制約 | approved-outbound で**自前 firewall を持ち込めない。**オンプレ接続は Application Gateway 必須。**outbound ログ未対応** | セットアップが複雑。RFC1918 必須、最小 `/27` |

**Managed VNet を規制案件で選びにくい理由:**
- **Azure Portal UI での作成が未対応**(Bicep / Terraform / `az rest` のみ)。
- **自前 Azure Firewall を持ち込めない。**`AllowOnlyApprovedOutbound` + FQDN ルールで**マネージド Firewall が自動作成され課金される**(既定 SKU = Standard、**デプロイ後に SKU 変更不可**)。
- **outbound トラフィックのログ機能が未対応**と比較表に明記。
- マネージド Private Endpoint は**顧客サブスクリプションに NIC として現れない**(可視性なし)。
- モードは一方向。`AllowInternetOutbound` → `Disabled` 不可、`AllowOnlyApprovedOutbound` → `AllowInternetOutbound` 不可。**有効化後の無効化も不可。BYO VNet からの移行パスもない。**

> **「出口通信のログを保全できない」「Firewall が自分のテナントにない」の 2 点は、通信ログ保全を求める規制要件に対する説明が難しい。**IP 空間重複という運用上の事情がない限り、**BYO VNet + 自前 Azure Firewall(ログを Log Analytics に集約)が説明性の面で有利**というのが本ドキュメントの判断(公式にこの優劣の記述はない)。

**Managed VNet の対応リージョンには Japan East が含まれる。**

---

## 2. BYO VNet(Standard agent setup)の設計

### 委任サブネット要件

| 項目 | 値 |
|---|---|
| 委任先 | `Microsoft.App/environments` |
| 最小サイズ | **`/27`**(後から変更不可) |
| 推奨サイズ | **`/24`**(hosted agent がある本番) |
| 50 同時セッションに必要 | **`/26` 以上**(`/27` は約 17 セッションが上限) |
| 共有可否 | **Foundry リソースごとに専用サブネット必須**(VNet は共有可) |
| アドレス範囲 | **RFC1918 のみ。**パブリック IP レンジ・CGNAT・`44.x.x.x` は不可 |
| Class A(`10.x`) | **特定リージョンのみサポート** |
| リージョン | **Foundry リソースと VNet は同一リージョン必須** |

> **⚠ 日本リージョンの非対称:** **Japan East は Class A(10.x)対応、Japan West は非対応。**国内 DR で West を使う場合、委任サブネットは 172.16-31.x または 192.168.x を割り当てる必要がある。

**ピアリング先 VNet も含めて、予約レンジ(`169.254.0.0/16`、`172.30.0.0/16`、`172.31.0.0/16`、`100.64.0.0/11` 等)と重複してはならない。**ピアリング VNet は一意で重複しない IP レンジが必須で、重複が避けられない場合は Managed VNet を使えと明記されている。

### BYO 必須リソースと Cosmos DB の RU/s

Standard setup は **Storage / AI Search / Cosmos DB の 3 つすべて**を渡さないと capability host 作成が失敗する。

**Cosmos DB はアカウント合計 3,000 RU/s 以上が必須**(コンテナーは 3〜5 個 × 各 1,000 RU/s。基本 3 個+Responses API 利用エージェントの初回起動で 2 個が追加作成される。排他ではなく追加関係で、Responses 利用時はプロジェクトあたり実質 5,000 RU/s)。**複数プロジェクトならプロジェクト数分を乗算する。**RU/s 不足は capability host プロビジョニング失敗の直接原因。

| コンテナー | 用途 | ランタイム |
|---|---|---|
| `thread-message-store` | エンドユーザー会話 | Classic |
| `system-thread-message-store` | 内部システムメッセージ | Classic |
| `agent-entity-store` | エージェントメタデータ | Classic |
| `agent-definitions-v1` | エージェントメタデータ + バージョン | **New** |
| `run-state-v1` | 内部メッセージ + 会話 | **New** |

> **⚠ capability host は作成後に更新できない。**構成変更には capability host の削除・再作成が必要(プロジェクト削除は不要。ただし削除で既存エージェントの会話・ファイルへのアクセスは失われる)。**IaC の冪等更新が効かない最大のポイント。**

**なお BYO VNet でもデータリソースは「platform-managed」を選べる**(テンプレート `11-private-network-basic-vnet`)。**「閉域にしたいがデータストアの運用は持ちたくない」場合の選択肢**として覚えておく。BYO データリソースが要るなら `15-private-network-standard-agent-setup`。

### Private Link のサブリソースと DNS ゾーン

| リソース | サブリソース(group ID) | Private DNS ゾーン |
|---|---|---|
| **Foundry** | `account` | `privatelink.cognitiveservices.azure.com` / `privatelink.openai.azure.com` / `privatelink.services.ai.azure.com` |
| Azure AI Search | `searchService` | `privatelink.search.windows.net` |
| Azure Cosmos DB | `Sql` | `privatelink.documents.azure.com` |
| Azure Storage | `blob` | `privatelink.blob.core.windows.net` |
| Container Registry(hosted agent) | `registry` | `privatelink.azurecr.io` |
| Application Insights | AMPLS 経由 | `privatelink.monitor.azure.com` ほか 3 種 |

**落とし穴:** Foundry リソースをデプロイしても、**AI Search / Storage / Cosmos DB の Private Endpoint は自動作成されない。**各リソース側で別途作成が必要。

**オンプレ DNS を使う場合:** `privatelink` サブドメインを VNet の Private DNS ゾーンに委任するか、条件付きフォワーダーを **Azure DNS 仮想サーバー `168.63.129.16`** に向ける。

**Private Endpoint 側の制限:** VNet と**同一リージョン・同一サブスクリプション**に配置必須。**Approved 状態の PE のみトラフィックを通す。**VNet に **`172.17.0.0/16` は使用不可**(Docker bridge 予約)。

### トラフィックフロー

- **Hosted agent:** Client → Foundry endpoint → 委任サブネット内の **Micro VM** → Tools Service → **Data Proxy** → PE 経由で顧客リソース
- **Prompt agent:** Client → Foundry endpoint → Tools Service → Data Proxy → PE 経由(Micro VM を経由しない)

Micro VM は専用 NIC を持ち自身の送信は直接出るが、**ツール呼び出しは必ず single-tenant data proxy を経由する。**data proxy はプロジェクトごとに 1 つの専用インスタンス。

### Firewall / NSG / UDR

**許可が必要な FQDN / サービスタグ:**

| シナリオ | FQDN / タグ |
|---|---|
| Agents | `*.identity.azure.net`、`login.microsoftonline.com`、`*.login.microsoftonline.com`、`*.login.microsoft.com` または **`AzureActiveDirectory` サービスタグ** |
| Evaluations & Traces | `settings.sdk.monitor.azure.com`、`*.livediagnostics.monitor.azure.com`、`*.in.applicationinsights.azure.com`、`AzureMachineLearning` タグ |
| Fine-tuning | `raw.githubusercontent.com`(ポータルでキュレート済みサンプルデータセットを選ぶ場合) |
| Managed VNet 追加分 | `mcr.microsoft.com` |

加えて **Azure Container Apps 側の Managed Identity 系 FQDN** も許可が必要。

> **⚠ TLS インスペクション禁止(最重要):** 「Firewall で TLS インスペクションが行われ自己署名証明書が付加されないことを確認せよ」と明記され、Architecture Center 側でも「**このトラフィックに Azure Firewall の TLS インスペクションを適用するな。検査時の証明書がエージェントの接続を壊す。**」と明言されている。
>
> **多くの日本の金融機関で標準になっている「出口 Firewall での SSL 可視化」ポリシーと正面衝突する。**設計初期に例外承認を取る必要がある。

**サブネット別の統制**は [01 章の Baseline アーキテクチャ](./01-official-baselines.md#b-baseline-本番の出発点-waf-が-ai-ワークロードの推奨アーキテクチャ-と名指し)の表を参照。公式の追加推奨として、**強制トンネリングをサポートする全サブネットに適用する**(egress を想定しないサブネットにも多層防御として)、**Azure Firewall はリージョン内の全可用性ゾーンにデプロイする**(egress の単一障害点であるため)、**高い同時 outbound 接続数がある場合は複数パブリック IP を構成して SNAT ポート枯渇を回避する**、が挙げられている。

---

## 3. 閉域で使えない機能の一覧(設計の出発点)

### エージェントツールの互換性

| ツール | 状況 | トラフィック経路 |
|---|---|---|
| MCP Tool(Private MCP) | 対応 | **自 VNet サブネット経由** |
| Azure AI Search | 対応 | **Private Endpoint 経由** |
| OpenAPI tool / Azure Functions / A2A | 対応 | 自 VNet サブネット経由 |
| Function Calling | 対応 | Microsoft バックボーン |
| Foundry IQ | 対応 | MCP 経由 |
| **Code Interpreter** | **部分** | **ファイルの上り下りを伴わないシナリオのみ動作。**回避策は SDK でコンテナーを作り `container_id` を渡す(**ポータル UI では不可**) |
| **Bing Grounding / Websearch / SharePoint Grounding** | 動くが**パブリックエンドポイント経由** | ↓ 下記の警告 |
| Fabric IQ | 部分 | Fabric アイテム種別依存(Power BI セマンティックモデルは**パブリックアクセスのみ**) |
| **Fabric Data Agent** | **非対応** | Fabric 側でパブリックネットワークアクセス有効が必須 |
| **Logic Apps** | **非対応** | 開発中 |
| **File Search** | **非対応** | 開発中 |
| **Browser Automation** | **非対応** | 開発中 |
| **Computer Use** | **非対応** | 開発中 |
| **Image Generation** | **非対応** | 開発中 |

> **金融・公共での決定的な論点:** Bing Grounding / Websearch / SharePoint Grounding は「動く」が**パブリックインターネット経由である**とドキュメント自身が明記している。「すべての通信をプライベート網に閉じる」要件があるなら、これらは**要件を満たさない。**ブロック手段として **Azure Policy による利用禁止**が公式に案内されている。
>
> さらに Architecture Center 側では「**web search ツールは `api.bing.microsoft.com` を呼ぶが、Agent Service が内部機構で呼ぶため egress サブネットを完全にバイパスする**」と明記。「443 を許可すれば Firewall を通るだろう」という想定が成り立たない。**全ツールを実測で検証せよ**と書かれている。

**File Search 非対応の影響が最も大きい。**閉域では **Azure AI Search ツール(PE 経由・対応)** に寄せる必要がある(→ [04 章の A2/A3](./04-usecase-chat-rag.md))。Blob Storage のファイルを File Search で使うことも別途「非対応」と明記されている。

### 機能レベルの非対応

| 機能 | 状況 |
|---|---|
| **Traces** | **非対応**(プライベート Application Insights での VNet サポートが未提供) |
| **Memory** | **VNet 非対応** |
| **Work IQ** | **VNet 統合非対応** |
| Evaluations の Synthetic Data Generation | **非対応**(自前データを持ち込んで評価する) |
| **Workflow Agents** | inbound は対応。**VNet 注入による outbound は非対応** |
| **AI Gateway(APIM)** | 新ポータルからプライベート Foundry に対して作れるが**自動的にパブリックになる。**Azure portal でゲートウェイ側のネットワーク分離を別途設定する必要 |
| **Foundry MCP Server** | ネットワーク分離未対応(Private Link 裏のリソース不可) |
| Teams / M365 への公開 | 可能だが**パブリックネットワーク無効プロジェクトではポータル不可・REST のみ** |
| **hosted agent のエンドポイント** | **現プレビューでは公開のまま。**ユーザーごとの分離はネットワークではなく ID ベースのセッション分離 |

> **Traces 非対応は監査要件に直撃する。**可観測性が要る規制ワークロードで、トレースだけパブリック Application Insights になる構成をどう説明するかが課題になる。**監査ログ設計を Purview Audit / Defender アラート / APIM ログ / アプリ独自の監査ログの組み合わせで再設計する**必要がある。

### その他の運用上の制約

- **ACR のプライベート化は 2026-06-25 以降に作成したプロジェクトのみ。**それ以前のプロジェクトは ACR にパブリックエンドポイントが必要。
- **VNet 化後は公開インターネット上の端末から `azd up` / `azd deploy` ができない**(データプレーン呼び出しが 403)。**VNet 内のセルフホスト GitHub Actions runner / Azure DevOps agent が推奨パターン**で、CI/CD 基盤の追加コストになる。
- **ポータルアクセス:** パブリックアクセス無効の場合、Foundry ポータルのプロジェクトレベル機能はすべてネットワークアクセスを要する。開発者は jump box / ピアリング VNet / ExpressRoute / S2S VPN 経由でアクセスする(Azure Bastion → jump box → PE が公式パターン)。
- **削除順序:** Foundry リソースと VNet は最後に削除する。VNet 削除前に Foundry リソースを削除し **purge** する。失敗すると `serviceAssociationLinks` エラーで VNet が消せなくなる。
- **AI Search のインデクサは `executionEnvironment` を `"Private"` にしないと PE を越えられず「サイレントに失敗して空インデックス」になる。**

---

## 4. Network Security Perimeter という代替(Private Link とは排他)

Foundry リソースは **NSP に関連付けできる。**PaaS リソース群を論理境界でまとめ、inbound/outbound アクセスルールを適用し、アクセス判断を集中ログ化する。

| 項目 | 内容 |
|---|---|
| アクセスモード | **Learning**(ログ観測のみ)→ **Enforced**(ルール適用)の順で移行 |
| `publicNetworkAccess` との関係 | **Enforced では NSP ルールが優先し PNA を実質上書き** |
| Inbound ルール | IP レンジ(CIDR)またはサブスクリプション(マネージド ID)スコープ |
| Outbound ルール | FQDN 宛先 |
| ログ | 診断設定で `NspAccessLogs` テーブルへ |

**重大な注意点:**
- NSP は**データプレーントラフィックを統制する。コントロールプレーン操作は別途制限しない限り通る場合がある。**
- **Enforced モードでも、診断ログ出力先への送信が NSP ルールでフィルタされるのは Microsoft Entra ID 認証を使う場合のみ。**API キー認証のリクエストは NSP perimeter claim を持たないため**ログトラフィックが NSP でブロックされない。**完全な NSP 準拠には Entra ID 認証が必須。
- **Private Endpoint / UDR を使う構成とは併用できない。**Baseline アーキテクチャは「PE と UDR を使うため NSP 機能をサポートしない」と明記。

> **NSP と Private Link は排他的な二択。**NSP は「PaaS 群の論理境界 + 集中ログ」が主眼で、VNet を持たない / 持ちたくない構成向け。**エージェントの egress をサブネットに落として Firewall で見たいなら Private Link + BYO VNet 一択。**

---

## 5. データ主権とデータ所在

### デプロイ種別と処理範囲

**全デプロイ種別共通で、保存時データは指定した Azure ジオグラフィに留まる。**異なるのは**推論時の処理場所。**

| データゾーン | 処理範囲 |
|---|---|
| **United States** | 米国内 |
| **European Union** | **Azure EU Data Boundary** 内(仏・独・伊・蘭・諾・波・西・瑞・スイス)。**事前通知なくリージョンが追加されうる** |
| **Asia Pacific (APAC)** | **オーストラリア、日本、韓国、シンガポール、インド。**事前通知なくリージョンが追加されうる |

> **日本の金融 / 公共における決定的論点:** **「日本国内のみで処理」を保証できるのは `Standard`(リージョナル)または `ProvisionedManaged`(Regional Provisioned)だけ。****APAC Data Zone は日本を含むが豪・韓・星・印も含む**ため「国内処理」にはならない。
>
> ただし Standard / Regional は「モデル可用性とスループットが限定されうる」「高い継続的ボリュームでは遅延のばらつきが大きくなりうる」と明記されており、**モデル選択肢とスループットを犠牲にする**トレードオフになる。

**⚠ 公式ドキュメント間の不整合:** `foundry/concepts/architecture` は「data zone は US または EU 内に留まる」と書いており **APAC に触れていない。**`deployment-types` 側(US/EU/APAC を明記)が正。**この記述だけを読むと誤った提案になる。**

**Azure Policy でデプロイ種別を制限できる**(`Microsoft.CognitiveServices/accounts/deployments` の `sku.name` を対象にしたポリシールール)。「Global Standard を作らせない」を組織的に強制できる。

**Claude のデプロイ種別:** Global Standard(全 Claude モデル)と **Data Zone Standard (US) のみ**(Azure ホスト版の一部モデル)。**EU / APAC の Data Zone デプロイは提供されていない。**

### Foundry が保存するもの・保持

**処理されるデータ:** プロンプトと生成コンテンツ / アップロードデータ(Files API・vector store)/ **ステートフルエンティティのデータ(Responses API、Threads、Stored completions)** / 学習・検証データ。

**明示的なコミットメント:** プロンプト・完了・埋め込み・学習データは、他の顧客に提供されず、**モデル提供者(OpenAI 等)にも提供されず**、モデル改善に使われず、**許可・指示なしに基盤モデルの学習に使われない。**モデルはステートレスで、プロンプトも完了もモデル内に保存されない。

保存されるデータは Foundry リソース(顧客の Azure テナント内)に**リソースと同一ジオグラフィで**保存され、**既定で常に AES-256 で暗号化**され、**顧客がいつでも削除できる。**

**Agent Service のデータ所在:** 「Foundry Agent Service のエンドポイントはリージョナルで、データはエンドポイントと同じリージョンに保存される。」

### 不正使用監視と人間によるレビュー(規制案件での説明対象)

濫用の指標が検出されると、**顧客のプロンプトと完了のサンプルがレビュー対象として選択されうる。**レビューは既定で自動手段(LLM を含む)、必要に応じて**人間レビュー**が追加される。人間レビュー用のデータストアは顧客リソース単位で論理分離され、**顧客のプロンプト / 生成物は Foundry リソースがデプロイされた Azure ジオグラフィに保存される。**認可された Microsoft 従業員が、request ID によるポイントクエリ、Secure Access Workstations、マネージャー承認の Just-In-Time 経由でアクセスする。

**Modified abuse monitoring(データ保存と人間レビューの停止)** をマネージド顧客は申請できる(Limited Access レビュー)。承認されると上記のデータ保存と人間レビューは行われない(**自動レビューは継続されうる**)。

> **⚠ 監査エビデンスの取り方:** Azure portal の Foundry リソース Overview → **JSON View**、または `az cognitiveservices account show` で、**Capabilities リストに `{"name":"ContentLogging","value":"false"}` が現れるのは abuse monitoring 用データ保存がオフのときだけ。**オフでない場合このプロパティは出力に現れない。**「申請したから大丈夫」ではなく、この値で確認する。**

**プレビュー機能の例外:** 「Azure Preview 機能(プレビュー中の Models sold by Azure を含む)は、**abuse monitoring を含めて異なるプライバシー慣行を採用する場合がある。**」

### CMK(顧客管理キー)

**適用範囲:** Foundry リソースに関連付けられたストレージに保存される保存時データ(**プロジェクト成果物・アップロードファイル・評価データを含む**)。

| 項目 | 要件 |
|---|---|
| キーストア | Azure Key Vault または Azure Managed HSM |
| リージョン | **キーストアと Foundry リソースは同一リージョン** |
| キー保護 | **論理削除(soft delete)と purge protection が必須** |
| マネージド ID | Foundry リソースの**システム割当 + ユーザー割当の両方**が前提 |
| ロール | Key Vault Crypto User(Azure RBAC 推奨) |
| キー種別 | **RSA、最小 2048 bit** |

**⚠ リージョン制限:** 「基盤の Azure AI Search インフラのキャパシティ制約により、**CMK 暗号化は現時点で一部のリージョンでのみ利用可能。**」対応リージョンは Azure AI Search のリージョンサポートページを参照する必要がある。**日本リージョンでの可否は案件着手時に必ず個別確認する。**

**⚠ プライベートネットワーク時のキーストア構成は 2 択しかない:**
1. **Private Link endpoint + 「信頼された Microsoft サービスを許可」有効**(推奨構成)
2. 「信頼された Microsoft サービスを許可」のみ(PE なし)

つまり **「Key Vault を完全にプライベート化し、trusted services バイパスも切る」構成は Foundry の CMK ではサポートされない。**「バイパス全面禁止」ポリシーとの調整が必要。

**不可逆性:** プロジェクトは Microsoft 管理キーから CMK に更新できるが**逆は不可。**プロジェクト CMK は同一キーストア内のキーにしか更新できない。**キーを失効 / 削除すると、そのキーで暗号化されたデータはキーが復元されるまでアクセス不能。**また**一部のプレビュー機能は CMK 非対応。**

---

## 6. コンプライアンス統制

### Azure Policy(モデルデプロイ)

| ポリシー | 目的 | ステータス |
|---|---|---|
| **Foundry model deployments should only use approved models** | 承認済みモデル / パブリッシャーのリストに限定 | **GA** |
| **Foundry model deployments should meet eligibility requirements** | `onlyAllowDirectFromAzure` / **`denyPreviewModels`** で属性ベース制御 | プレビュー |
| Foundry Tools resources should have key access disabled | ローカル認証(API キー)を無効化 | — |

**`denyPreviewModels=true` は「プレビューモデルを本番に持ち込まない」統制をプラットフォームレベルで実装できる。**本番サブスクリプションには入れておく。

**⚠ asset ID はプレフィックスマッチ。**末尾スラッシュなしの `azureml://registries/azure-openai/models/gpt-5` は **GPT-5.2 や GPT-5.4 にもマッチしてしまう。**特定モデルに限定するには**末尾にスラッシュ**を付ける。

**⚠ model router を使う場合:** パブリッシャー許可リストに `Microsoft` を含める必要がある(Microsoft が model router のパブリッシャー)。**Claude にルーティングするなら `Anthropic` も追加。**ポリシーは model router が選択する配下モデルにも適用される。

**適用タイミング:** ポリシー割当は即時反映されない。**最低 15 分待つ。**コンプライアンスダッシュボードへの反映は評価サイクル(通常最大 24 時間)。Foundry ポータルへの反映は最大 30 分。

**その他:** プレビュー機能の抑止はタグ `AZML_DISABLE_PREVIEW_FEATURE=true`(サブスク / RG / リソース単位)でポータルのプレビュー UI を非表示化でき、カスタム RBAC(`notDataActions` / `notActions`)で API レベルのブロックもできる。

### API キーの無効化(`disableLocalAuth`)

**Agent Service と Evaluations は API キーでは動かない**(Entra ID 必須)ので、エージェント基盤を採る時点で Entra は前提。加えて `disableLocalAuth` でキーを完全に殺す。

> **⚠ 伝播遅延(見落としがち):** コントロールプレーンには即座に反映されるが、**認証を強制する共有ゲートウェイはキャッシュ更新まで既存キーを受け付け続ける。**通常は数分だが、**リージョン・負荷・ゲートウェイキャッシュ状態によっては数時間かかりうる。**「即座の遮断」を前提にしたセキュリティ運用はできない。**古いキーでデータプレーン要求を投げて HTTP 401 が返ることを確認してから完了とみなす。**
>
> **鍵漏洩時の手順書に「止めたと宣言できるまで数時間の窓が開く可能性」を明記する。**

### Microsoft Purview 統合(プレビュー)— 規制案件での期待値調整

サポートされるのは DSPM for AI / Auditing / Data classification / Sensitivity labels / DLP / Insider Risk Management / Communication compliance / eDiscovery / Data Lifecycle Management / Compliance Manager。**Encryption without sensitivity labels は非対応。**

**⚠ 決定的な制約が 4 つある:**

1. **Data Security Policies は、Entra ID の「ユーザーコンテキストトークン」を使う API 呼び出しにしか適用されない。**それ以外の認証シナリオでは、ユーザー相互作用は Purview Audit と Activity Explorer の分類にしか現れず、**ポリシーによる強制は行われない。**
2. **Purview 統合には Foundry エージェントのデータやコンテキストは含まれない。**「Foundry エージェント統合のサポートは現時点で提供されていない」と Defender ドキュメントに明記。
3. **Purview 統合は現時点でネットワーク分離をサポートしない。**
4. **課金:** データセキュリティポリシーは pay-as-you-go メーター。**PAYG 課金が Purview 側で設定されていないと Purview Audit 統合しかサポートされない。**

> **2 と 3 の組合せが致命的:** 「ネットワーク分離した Foundry でエージェントを動かす」という規制業界の標準構成では、**Purview による DLP / 分類は現時点でほぼ機能しない。DSPM for AI を前提としたコンプライアンス説明はできない。**

### Microsoft Defender for Cloud(AI services プラン)

3 コンポーネント: **Suspicious prompt evidence**(疑わしいプロンプト / 応答をアラートエビデンスとして受信。機密データは自動リダクト)/ **Data security for AI interactions**(Purview 側の有償機能で、Defender プランには含まれない)/ **AI model security**(Azure ML Registries のモデルをスキャン)。

検出対象は「Foundry のマネージド推論エンドポイント上に構築された AI ワークロード」で、**jailbreak およびユーザー入力攻撃を検出**する。**Azure Government / 21Vianet は非対応。**

### Azure Security Baseline での注意点

MCSB v1.0 ベースで「古いガイダンスを含む可能性がある」と警告付きだが、**Customer Lockbox が非対応**と記載されている点は金融 / 公共で問い合わせが来る典型項目。**最新状況は Microsoft に個別確認する。**(DLP・機微データ検出が "False" になっているのは Purview 統合が後から追加されたことによる表の陳腐化の可能性が高い。)

---

## 7. 評価とレッドチーミングのリージョン制約(日本案件で必ず効く)

| 機能 | 対応リージョン |
|---|---|
| バッチ評価 | 広範(**Japan East / Japan West を含む**) |
| **リスク・安全性評価器** | **East US 2 / North Central US / France Central / Sweden Central / Switzerland West / Australia East のみ** |
| Groundedness Pro | East US 2 / Sweden Central のみ |
| Protected material | **East US 2 のみ** |
| **AI Red Teaming** | **公式2ページ間で記載が揺れる(evaluation-regions ページは East US 2 / North Central US の2つ、ai-red-teaming-agent ページは +France Central / Sweden Central / Switzerland West の5つ)。いずれにせよ日本・APAC 非対応** |

> **本番推論は Japan East、安全性評価と Red Teaming は別リージョンの評価専用プロジェクト**という分離構成になる。**プロンプト・応答が評価のために国外に渡る**ため、法務確認が必須。評価だけなら Agent 用のフル構成(Cosmos DB / AI Search / capability host)は不要で、**評価専用の Bicep テンプレート**が用意されている。
>
> 加えて **Guardrails の Task adherence は「データが指定 Geo 外(US/EU)で処理される可能性」が明記されている。**

---

## 8. ソブリンクラウド(Azure Government)

| 項目 | 内容 |
|---|---|
| ポータル | https://ai.azure.us/ |
| リージョン | US Gov Arizona / US Gov Virginia |
| エージェント種別 | Prompt agents = 対応 / Workflows = プレビュー / **Hosted agents = 非対応** |
| 利用可能ツール | Code Interpreter / File Search / Azure AI Search / Azure Functions / Function calling |
| **非対応ツール** | **Web search / Grounding with Bing / Image Generation / Browser Automation / Computer Use / Microsoft Fabric / SharePoint / MCP servers / A2A / OpenAPI tool** |
| 非対応機能 | Serverless endpoints / Content Understanding / Agents playground / **Fine-tuning** / **Batch jobs** / Azure OpenAI Evaluation / VS Code 拡張 |
| 公開 | Entra Agent Registry への登録は可。**Teams / M365 Copilot への公開は非対応** |
| SDK | `azure-ai-projects` 2.0.0 以降。スコープは `https://ai.azure.us/.default` |

> **プレビュー機能とコンプライアンス認定の関係を明文化しているのはこのページだけ:** 「**Preview 表記の機能は、GA 機能と同じコンプライアンスコミットメント(FedRAMP, DoD IL5, CJIS 等)を伴わない場合がある。**規制ワークロードで使う前にセキュリティ・コンプライアンスチームで確認せよ。」
>
> **日本の政府調達(ISMAP 等)でも同種の論理が使えるが、ISMAP への言及はドキュメント上に見つからなかった。**日本固有の認証状況は Microsoft Trust Center / Service Trust Portal 側で個別確認が必要。

---

## 9. エッジ・オンプレ・ハイブリッド

**「オンプレで Foundry を動かす」には 3 つの別物がある。**名前が似ているので最初に切り分ける。

| 選択肢 | 何か | ライフサイクル |
|---|---|---|
| **Foundry Local** | **エンドユーザー端末上**でアプリに AI を埋め込むための SDK + ランタイム | **GA**(公式ブログで 2026-04-09 に GA 宣言: https://devblogs.microsoft.com/foundry/foundry-local-ga/ 。docs ページにはラベルなし) |
| **Foundry Local on Azure Local** | **オンプレ K8s 上のエンタープライズ推論基盤**(Arc 拡張) | **プレビュー、かつ申請制** |
| **Foundry Tools の切断コンテナ** | Speech / Language / Vision / Document Intelligence 等を**エアギャップで動かす** | サービスごとに GA / preview が異なる |

### 9.1 Foundry Local(端末上)

「ユーザーのデバイス上で完全に動作するアプリケーションを出荷するための、エンドツーエンドのローカル AI ソリューション」と定義されている。

- **公式ブログで 2026-04-09 に GA 宣言済み**( https://devblogs.microsoft.com/foundry/foundry-local-ga/ )。ただし docs の概要ページにも入門ページにも GA / preview のラベル・バナーが無い点は変わらない(初版の「Microsoft は GA と明言していない」という記述は撤回)。(なお「Foundry Local is available in preview」という記述は **Azure Local 版の記事内にのみ**存在する。同名製品の混同に注意。)
- **Windows / macOS(Apple silicon)/ Linux。Azure サブスクリプション不要。**ランタイムは ONNX Runtime で、アプリへの追加サイズは約 20MB。
- **ハードウェアアクセラレーションは自動。**「利用可能なハードウェアを検出し最良の実行プロバイダーを選ぶ。**GPU と NPU** で高速化し、無ければ CPU にシームレスにフォールバックする。ハードウェア検出コードは不要」。Windows 向けには専用パッケージがあり、Windows ML ランタイムと統合して「同じ API サーフェスでより広いハードウェアアクセラレーション」を提供する。
- **モデルカタログは意図的に絞られている。**対象は**チャット補完(GPT OSS / Qwen / DeepSeek / Mistral / Phi)と音声書き起こし(Whisper)の 2 系統のみ。**「Foundry Local は**汎用のモデル実験用ではなく本番アプリの出荷用**に設計されている」と明記。**埋め込みモデル・ビジョンモデルの記載はない。**
- **API は OpenAI 互換**で、「**Responses API のフォーマットを含む**」。ただし「フォーマットをサポート」であり、クラウド版 Responses API のステートフル機能まで再現するとは書かれていない。SDK は C# / JavaScript / Rust / Python。
- **ローカル HTTP サーバーはオプション扱い。**「多くの組み込みアプリシナリオでは SDK を直接使え。別サーバーのオーバーヘッドなしでインプロセス推論する」。FAQ でも「これは Web サーバーと CLI ツールか? → **いいえ**」と明言している。

> **⚠ サーバー用途は明確に否定されている(逐語):**
> 「Foundry Local は**一度に単一ユーザーがモデルにアクセスする、ハードウェア制約のあるデバイス向けに最適化されている。**サーバーハードウェアに technically インストールして動かすことはできるが、**サーバー推論スタックとして設計されていない。**vLLM や Triton Inference Server のようなサーバー志向のランタイムは、同時リクエストのキューイング、継続的バッチング、多数の同時クライアント間での効率的な GPU 共有のために作られている。**Foundry Local はこれらの機能を提供しない。**……**複数の同時ユーザーにモデルを提供する必要があるなら、専用のサーバー推論フレームワークを使え。**」

推論はローカル完結で、ネットワークを使うのはモデル / 実行プロバイダーの初回ダウンロードと、任意の診断ログ共有のみ。

### 9.2 Foundry Local on Azure Local(オンプレ K8s)

**別 SKU で、ドキュメントも `azure-sovereign-clouds` 配下の別セット。**「Arc 対応 Kubernetes クラスター上に AI モデルをデプロイして実行し、Kubernetes ネイティブな運用を行う」もの。

**⚠ プレビューかつ申請制。**「Foundry Local on Azure Local のデプロイは**プレビュー期間中はリクエストベースでのみ利用可能**」と明記され、専用の申請フォームが用意されている。**GA 時期の記載は見つからなかった。**

| 項目 | 内容 |
|---|---|
| 形態 | Azure Arc 拡張としてインストール。inference operator が状態を調停し、`Model` / `ModelDeployment` の CRD で宣言的に管理 |
| 推論エンジン | **ONNX-GenAI(CPU / GPU)** または **vLLM(GPU 専用、高スループット向け)** |
| 対応 | 生成 AI 推論に加え、**Predictive AI 推論**(分類・スコアリング等の非生成モデル)も可能。マルチモデル同時配信可 |
| エンドポイント公開 | 内部 Service または **Kubernetes Gateway API**。API キー / Entra ID トークン検証 / TLS で保護 |
| リージョン | 18 リージョン。**Japan East を含む** |
| 前提 | Arc 接続、クラスター容量、GPU シナリオでは検証済みドライバー / プラグイン、クラスターレベル権限、証明書・API キー運用体制 |

**Azure Local の具体バージョン、GPU SKU、最小ノード数は概要ページに記載がなかった。**

**切断(disconnected)運用時の差分:** 拡張機能を **expansion pack** として事前にダウンロード・インポートし、モデルはローカルのコンテナレジストリから取得する。Istio・Gateway API CRD・Endpoint Picker イメージが同梱されるので**デプロイ時のアウトバウンド接続が不要。**証明書は `azure-cert-manager` が使えず `cert-manager` + `trust-manager` を導入する。**テレメトリは Microsoft へ送信されない。**認証はパブリックな Entra ID エンドポイントではなく**環境内の Active Directory** と統合する。認可は Azure RBAC で、**`Contributor` がコントロールプレーン書き込みに加えてデータプレーンの推論操作(`predict` / `chat/completions`)まで含む**点が接続環境と異なる。

**サイジングの注意:** マルチレプリカ vLLM は `ModelDeployment` あたり Endpoint Picker Pod を 1 つ追加し、既定でメモリ request 約 512MiB / limit 2GiB。**`az aksarc create` の既定ワーカーサイズ `Standard_A4_v2` は「通常小さすぎる」**と明記されている。

### 9.3 切断コンテナ(エアギャップでの Foundry Tools)

> **⚠ 本ドキュメント初版の記述を訂正:** 初版では「オンプレ / エアギャップの文書処理は Document Intelligence コンテナが唯一の選択肢」と書いたが、**これは不正確だった。****Vision の Read OCR コンテナも GA かつ切断対応**で、印刷 / 手書きテキストを JPEG・PNG・BMP・**PDF・TIFF** から抽出できる。
>
> **正確には:** 「**構造化文書抽出(Layout / 請求書・領収書・ID の Prebuilt / Custom Template)をエアギャップで行える唯一の選択肢が Document Intelligence コンテナ**。単純な OCR だけなら Vision Read コンテナも選べる」。なお **Content Understanding にはコンテナが存在しない**ため、**マルチモーダル文書処理をオンプレで、は不可。**

**切断対応の主な一覧:**

| サービス | コンテナ | ライフサイクル | 切断 |
|---|---|---|---|
| Document Intelligence | **バージョンごとに対応モデルが異なる**: v4.0 = Read / Layout **のみ**、v3.1 = Read / Layout / ID / Receipt / Invoice、v3.0 = Read / Layout / General Document / Business Card / Custom | v3.0 / v3.1 / v4.0 とも GA | **対応** |
| Vision | **Read OCR** | **GA** | **対応** |
| Speech | Speech to text / Custom Speech to text / Neural TTS | GA | 対応 |
| Speech | Speech language identification | プレビュー | **非対応** |
| Language | Key Phrase / Language Detection / Sentiment / NER / PII / CLU | GA | 対応 |
| Language | Summarization | パブリックプレビュー | 対応 |
| Language | Text Analytics for health / Custom NER | GA | **非対応** |
| Translator | Text Translation Standard | GA(**ゲート制**) | 対応 |
| Content Safety | Text Analyze / Image Analyze / Prompt Shields | パブリックプレビュー | **記述が不整合**(下記) |
| Decision | Anomaly Detector | GA | **非対応** |

> **⚠ ドキュメント間の不整合:** Content Safety の 3 コンテナは container-support ページで「切断環境でも実行できる」と明記されているが、**disconnected-containers ページの対応一覧には Content Safety が含まれていない。**エアギャップ案件で Content Safety を前提にするなら事前に確認する。

**承認プロセスとライセンス(見積もりに直結):**

- **申請フォーム提出後、10 営業日以内**に可否がメールで返る。**承認されたサブスクリプション ID で作成したリソースでのみ動作する。**
- アクセス条件は「**Microsoft の戦略的顧客またはパートナーとして識別されていること**」で、用途は「インターネット接続ゼロの環境 / たまにしか接続できない遠隔地 / データをクラウドに一切送れない厳格な規制下の組織」のいずれか。
- **コミットメントプランは暦年単位。**「プラン購入時に**全額が即座に課金される。**コミットメント期間中は**プランを変更できない。**ただし残日数分を按分価格で追加購入はできる」。
- **ライセンスファイルには有効期限があり、期限を過ぎるとコンテナを実行できない**(具体的な日数はドキュメントに記載なし)。新イメージを pull した後はライセンスの再取得が推奨されている。
- 使用量は出力マウント経由で記録し、REST エンドポイントから JSON レポートを取得する。

**Document Intelligence コンテナのハードウェア要件(すべて 8 コア):**

| コンテナ | 最小メモリ | 推奨メモリ |
|---|---|---|
| Read | 10 GB | 24 GB |
| Layout / Invoice / Business Card / Custom Template | 16 GB | 24 GB |
| General Document | 12 GB | 24 GB |
| Receipt | 11 GB | 24 GB |
| ID Document | 8 GB | 24 GB |

**接続コンテナ(切断でない場合)の注意:** ポート 443 と `*.cognitiveservices.azure.com` / `*.cognitive.microsoft.com`(Translator オンプレは `translatoronprem.blob.core.windows.net` も)の許可が必要で、**DPI(Deep Packet Inspection)は無効化が必須。**また「**既定ではコンテナ API にセキュリティがない**」ため、Istio / Nginx 等を前段に置くことが推奨されている。

### 9.4 ハイブリッド(クラウド + エッジフォールバック)の公式ガイダンスは存在しない

**Azure Architecture Center に「クラウド + エッジ推論フォールバック」のリファレンスアーキテクチャは見つからなかった。**AI アーキテクチャ索引にエッジ推論・ハイブリッド推論・オンプレ AI の記事は 1 本もなく、旧「AI at the edge」記事は索引へリダイレクトされて実体が消えている。`/azure/architecture/hybrid/` も 404。

**代替として使える公式材料:**
- **配置先の二択**(端末上 = Foundry Local / オンプレ K8s = Foundry Local on Azure Local)を示す Foundry Local 概要ページが、**唯一の公式なエッジ配置ガイダンス。**
- モデルライフサイクル記事の「Deployment option change」が MaaS / MaaP / **Self-hosting** の 3 戦略とトレードオフを整理しており、「セルフホストは最大の制御を与えるが、インフラ・管理・保守の責任が大きい」と明記している。
- ゲートウェイパターン(複数バックエンドルーティング)は技術的には Foundry Local(OpenAI 互換)とクラウドの切替に転用できるが、**これらはクラウド内の複数バックエンドを想定した記述で、エッジ→クラウドのフォールバックは対象外。****公式に検証されたパターンではない**ことを顧客に明示する。

**エッジ案件の判断軸:** 「完全にオフラインで推論する」なら Foundry Local か切断コンテナで、**Foundry のエージェント機能・ガードレール・観測性は一切使えない。**「基本はクラウド、通信断時のみローカル」というハイブリッドは、**公式の裏付けが無い自社設計**になることを前提に工数を積む。

### 補足: 「Windows AI Foundry」という製品は存在しない

現行ドキュメントでは **「Microsoft Foundry on Windows」に改称**されている。これは傘の名称で、中身は 3 つの技術:

| | Windows AI APIs | Foundry Local | Windows ML |
|---|---|---|---|
| 内容 | タスク別のすぐ使える AI モデル / API | すぐ使える LLM と voice-to-text | 自前 / 入手モデルを実行する ONNX Runtime フレームワーク |
| 対応デバイス | **Copilot+ PC のみ** | **Windows 10 以降 + クロスプラットフォーム** | Windows 10 以降 + クロスプラットフォーム |
| モデル配布 | Microsoft ホスト、アプリ間共有 | 同左 | アプリ自身が配布 |

公式の選択順序は「① Windows AI APIs で足りるか(Copilot+ PC 対象なら最速)→ ②足りない、または Windows 10 対応が必要なら **Foundry Local** → ③カスタムモデル / Hugging Face なら **Windows ML**」。3 つを組み合わせることもできる。

---

## 規制案件で早期に潰すべき論点(チェックリスト)

1. [ ] **国内処理要件** — Data Zone (APAC) は日本以外も含む。`Standard` / `ProvisionedManaged` 一択か、Global 許容かを法務と先に決める
2. [ ] **Firewall の TLS インスペクション** — Foundry は明示的に禁止。標準ポリシーの例外承認を先に取る
3. [ ] **Key Vault の trusted services バイパス** — CMK を使うなら必須(2 択しかない)
4. [ ] **CMK の日本リージョン可否** — AI Search 側のリージョン表で個別確認
5. [ ] **WAF ルール除外** — チャットで OWASP anomaly score が累積し突然 403。除外設計の承認を先に取る
6. [ ] **Purview による DLP** — **ネットワーク分離下では非対応、エージェントデータは対象外。**DSPM for AI 前提の説明は成立しない
7. [ ] **Traces** — プライベート App Insights 非対応。監査ログ設計を Purview Audit / Defender アラート / APIM ログ / アプリ独自ログの組合せで再設計
8. [ ] **会話 ID の認可** — Foundry はユーザー単位の会話認可を強制しない。アプリ側で BOLA 対策必須
9. [ ] **Customer Lockbox** — Security Baseline 上「非対応」。最新状況を Microsoft に個別確認
10. [ ] **ネットワーク構成の後戻り不能性** — アカウント作成時に確定。**PoC と本番でサブスクリプション / リソースグループを分ける**
11. [ ] **Claude を使うなら** — Foundry ガードレールが効かない。APIM の `llm-content-safety` かアプリ層で Content Safety を呼ぶ
12. [ ] **同時セッション 50 / サブスクリプション / リージョン** — 大規模利用ではサブスクリプション分割が必要になりうる
13. [ ] **評価の越境** — 安全性評価と Red Teaming が日本で動かない。国外へのデータ移送について法務確認
14. [ ] **プレビュー機能とコンプライアンス認定** — プレビューは GA と同じ認定コミットメントを伴わない可能性。使用機能を棚卸し
15. [ ] **abuse monitoring** — Modified abuse monitoring を申請したなら `ContentLogging=false` で実際に確認
