# 01. プラットフォーム基盤・プロジェクト・コントロールプレーン

[← 機能一覧 TOP](./README.md)

> **最終更新:** 2026-07-30(2026-07-29 の初版を一次情報に当てて検証・訂正。訂正内容は [TOP の更新履歴](./README.md#更新履歴)参照)

## 概要

Foundry リソース・プロジェクトのモデル、新旧ポータルの関係、コントロールプレーン(Operate)、RBAC・ネットワーク・暗号化・ポリシーなどのガバナンス機能を扱う。**新 Microsoft Foundry ポータルは GA 宣言済み**(「The new Microsoft Foundry portal is generally available (GA).」)だが、GA はコアシナリオ範囲であり、Operate(コントロールプレーン)の大半など一部機能はプレビュー継続である(出典: https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability )。

## リソース・プロジェクト

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Foundry resource | エージェント/モデル/ツールを単一リソースで統合管理。実体は `Microsoft.CognitiveServices/accounts`(kind: `AIServices`)で、旧 AI Services リソースの後継。プロジェクトは子リソース `accounts/projects` | GA(GAページで「Foundry projects: Fully supported at GA」) | 新/classic 両方+Azure portal | 対応 `az cognitiveservices account create --kind AIServices --allow-project-management` | 対応 `azure-mgmt-cognitiveservices` 13.7+ | https://learn.microsoft.com/en-us/azure/foundry/concepts/architecture ・ https://learn.microsoft.com/en-us/azure/foundry/how-to/create-projects | RP は Microsoft.CognitiveServices を継続。既存の RBAC/Policy がそのまま適用 |
| Upgrade Azure OpenAI → Foundry resource | AOAI リソースをエンドポイント・キー・状態(fine-tune、batch 等)を保持したまま Foundry リソースへ変換(kind: `OpenAI`→`AIServices` + `allowProjectManagement: true`) | GA(「Both services are generally available and supported before and after the upgrade」。opt-in) | classic ポータル+Azure portal(新ポータルの手順は記載なし) | 記載なし(Bicep/Terraform 推奨) | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/how-to/upgrade-azure-openai | ロールバック可(プロジェクト等の削除が前提)。CMK 利用リソースは申請フォーム経由のみ。既存 Private Endpoint 付きはポータル経由不可(削除→再作成 or IaC)。`previousKind` プロパティで判別可 |
| Auto-upgrade(AOAI→Foundry 自動アップグレード) | Microsoft が適格な AOAI リソースを自動アップグレード。`foundryAutoUpgrade` プロパティで状態確認・オプトアウト可 | 要確認(段階的ロールアウト中。ページに preview/GA ラベルなし) | Azure portal(「Resource upgrade」ブレード) | Bicep/Terraform で `foundryAutoUpgrade.mode` を設定可(**SDK の enum は Enabled / Disabled のみ**。「Deferred」は SDK リファレンスに存在せず要確認: https://learn.microsoft.com/en-us/dotnet/api/azure.resourcemanager.cognitiveservices.models.foundryautoupgrademode ) | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/how-to/upgrade-azure-openai-auto | Private networking / CMK / W&B 利用リソースは初期波では対象外。事前通知あり。ロールバックは手動アップグレードと同じ別手順 |
| Foundry project | Foundry リソース配下の子リソース(`accounts/projects`)。アクセス制御・データ分離の単位。親のネットワーク/セキュリティ設定を継承 | GA(「Fully supported at GA with end-to-end coverage」) | 新ポータル(Operate > Admin)+classic+Azure portal | 対応 `az cognitiveservices account project create` | 対応 `azure-mgmt-cognitiveservices` | https://learn.microsoft.com/en-us/azure/foundry/how-to/create-projects ・ https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability | 最初の「default」プロジェクトのみ OpenAI Batch / Fine-tuning / Stored completions、Speech fine-tuning 等に対応(非 default プロジェクトは機能制限あり) |
| Hub-based project(ハブベース) | Azure ML ワークスペース基盤(`Microsoft.MachineLearningServices/workspaces`)の旧型プロジェクト。classic ポータルでのみ利用可 | 非推奨予定(正式な廃止日は**未発表**のレガシー扱い。「New investments are focused on Foundry projects」「Not supported in the new Foundry portal」) | classic のみ(新ポータルでは非表示) | 対応(AML CLI/SDK 経由で継続利用可) | 対応(同左) | https://learn.microsoft.com/en-us/azure/foundry/what-is-foundry ・ https://learn.microsoft.com/en-us/azure/foundry-classic/what-is-foundry | 残す理由: prompt flow(**2027-04-20 廃止予定**。新規開発は非推奨で Microsoft Agent Framework への移行を要求)、Azure Language リソース等が未対応のため。**マネージドコンピュートは新ポータルの Foundry プロジェクトに対応済み**(パブリックプレビュー)なので、classic を残す理由には当たらない → [02-models](./02-models.md)。Agents は hub-based だと「Preview only」 |
| Migrate hub-based → Foundry project | ハブベースから Foundry プロジェクトへの移行ガイド(手動、5–10分想定)。移行対象: モデルデプロイ、データファイル、fine-tuned モデル、Assistants、vector store | 提供中(移行自体に preview 表記なし) | classic ポータル+Azure portal | Bicep 例あり | SDK 移行ガイドあり | https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/migrate-project | 自動移行ツールはなし(新規プロジェクト作成+接続再作成方式)。プレビュー Agent の state、OSS モデルデプロイは移行対象外 |

## ポータル・移行

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Foundry portal(新) | ai.azure.com の新体験。Home / Discover / Build / Operate / Docs の5セクション構成。Foundry プロジェクトのみ表示 | GA(コアシナリオ。一部機能は preview — 詳細は Feature readiness 表) | — | — | — | https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability | 「New Foundry」トグルで classic と相互切替。sovereign cloud は https://ai.azure.us/ (US Gov Virginia/Arizona) |
| Foundry (classic) portal | 旧ポータル。hub-based プロジェクト、スタンドアロン AOAI リソース、prompt flow、serverless API デプロイ等、新ポータル未対応機能の受け皿 | 継続提供(廃止日**未発表**。「legacy hub-based project workflows」の位置づけ) | — | — | — | https://learn.microsoft.com/en-us/azure/foundry-classic/what-is-foundry | classic の what-is ページは NOINDEX 設定。ドキュメント更新周期も classic は 365 日(新は 90 日)で投資差が明確 |
| Navigate from classic(移行ガイド) | 用語・機能・SDK・ポータルナビの新旧対応表。Assistants API→Responses API、Threads→Conversations 等 | 提供中 | — | — | — | https://learn.microsoft.com/en-us/azure/foundry/how-to/navigate-from-classic | 重要日程: Assistants API 廃止 2026-08-26 / Workflows 廃止 2026-12-01(詳細は [TOP の期限表](./README.md)) |

## コントロールプレーン・ガバナンス

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Foundry Control Plane(Operate) | サブスクリプション横断でエージェント・モデル・ツールのフリート管理(インベントリ、可観測性、コンプライアンス、セキュリティ)。Defender / Purview / Entra 統合 | ペイン別に混在: Overview / Assets / Compliance = パブリックプレビュー、Quota / Admin = GA | 新 Foundry ポータルのみ(「available through the Foundry portal only」) | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/control-plane/overview ・ https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability | 高度なガバナンス機能には AI gateway(APIM)の構成が前提。カスタムエージェント登録、Copilot Studio エージェントの取り込み等を含む |
| Management center(classic) | classic ポータルの管理ハブ(全リソース表示、クォータ、ユーザー/ロール管理)。新ポータルでは Operate セクションに置換 | classic のみ提供 | classic のみ | — | — | https://learn.microsoft.com/en-us/azure/foundry-classic/concepts/management-center | 新旧マッピング: Quota → Operate > Quota、Users → Operate > Admin |
| Azure Policy(組み込み: 承認済みモデル) | 「Foundry model deployments should only use approved models」— 承認済み発行元/モデル ID のみデプロイ許可 | GA(「Generally available」明記) | Azure portal (Policy) | 対応 `az policy` | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/how-to/model-deployment-policy | 旧名「Cognitive Services Deployments should only use approved Registry Models」(定義 ID は不変) |
| Azure Policy(組み込み: 適格性要件) | 「Foundry model deployments must meet eligibility requirements」— `onlyAllowDirectFromAzure` / `denyPreviewModels` 属性ベースの制御 | パブリックプレビュー(「This policy is in preview」明記) | Azure portal (Policy) | 対応 `az policy` | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/how-to/model-deployment-policy | 「プレビューモデルの本番デプロイ禁止」をポリシーで強制可能 |
| プレビュー機能の無効化 | タグ `AZML_DISABLE_PREVIEW_FEATURE=true`(サブスク/RG/リソース単位)でポータルのプレビュー UI を非表示化。カスタム RBAC(`notDataActions`/`notActions`)で API レベルのブロックも可 | 提供中(それ自体のプレビュー表記なし) | 新/classic 両ポータルで有効 | 対応 `az tag update` / `az role definition create` | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/how-to/disable-preview-features | ブロック可能な機能とリソースプロバイダーパスの一覧あり(Agent Service, Content Understanding, Fine-tuning, Evaluations, Content Safety, Tracing) |

## RBAC・認証

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Built-in RBAC roles | 組み込みロール5種: **Foundry User / Foundry Project Manager / Foundry Account Owner / Foundry Owner / Foundry Agent Consumer**。スコープは Foundry resource / project / 個別 agent | GA(ただしロール名を旧名〈Azure AI User 等〉から改名ロールアウト中。ロール ID・権限は不変) | 新ポータル(Operate > Admin)+Azure portal IAM | 対応 `az role assignment create`(改名中は GUID 指定を推奨) | **記載なし**(ロール割り当てのサーフェスとして記載があるのは Foundry ポータルの Admin ページ / Azure ポータル IAM / Azure CLI。**「SDK 非対応」と明記されているわけではない** — 2026-07-30 訂正) | https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry | fine-tune には data+control 両権限が必要(単独で両方持つのは **Foundry Owner** のみ。分離するなら Foundry User〈data〉+ Foundry Account Owner〈control〉)。**ロール ID(改称中はこれを使う)**: Foundry User `53ca6127-db72-4b80-b1b0-d745d6d5456d` / Foundry Owner `c883944f-8b7b-4483-af10-35834be79c4a` / Foundry Account Owner `e47c6f54-e4a2-4754-9501-8e0985b135e1` / Foundry Project Manager `eadc314b-1a2d-4efa-be10-5d325db5065e` / Foundry Agent Consumer `eed3b665-ab3a-47b6-8f48-c9382fb1dad6`。**⚠ 使ってはいけないロール**: 「Cognitive Services」で始まる組み込みロールと **`Azure AI Developer`**(名前に反して Azure ML ワークスペース / Foundry ハブ用で、Foundry プロジェクトにも hosted agent にも適用されない)。**agent スコープの割り当ては現時点でエージェントエンドポイントへのアクセスのみ評価**され、コントロールプレーン権限は付与しない。**ポータル UI からのデプロイ時のみ Foundry User が自動割り当てされ、SDK / CLI からのデプロイでは行われない。**classic の hub 向け RBAC は別ページ |
| Microsoft Entra 認証 / キーレス | Entra ID(OAuth2、スコープ `https://ai.azure.com/.default`)と API キーの2方式。本番は Entra ID 推奨。`disableLocalAuth` でキー無効化可 | GA | 全サーフェス | 対応 | 対応 `azure-identity` | https://learn.microsoft.com/en-us/azure/foundry/concepts/authentication-authorization-foundry | **Agents / Evaluations / Content Understanding / workflows / dataset タブは Entra ID 必須**(API キー不可)。カスタムサブドメインがトークン認証の前提 |

## ネットワーク・暗号化

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Private Link(インバウンド) | Foundry リソース/プロジェクトへのプライベートエンドポイント。DNS ゾーン3種(cognitiveservices / openai / services.ai の privatelink) | GA相当(ページにプレビュー表記なし) | Azure portal(Networking タブで公開アクセス Disabled を選択可。2026-07-28 更新版で手順掲載) | Bicep/Terraform サンプルあり | 同左 | https://learn.microsoft.com/en-us/azure/foundry/how-to/configure-private-link | 制限: Traces(VNet 非対応)、Workflow Agents(アウトバウンド注入非対応)、AI Gateway は部分対応。Agent ツール個別の対応可否表あり(File Search / Logic Apps / Browser Automation / Computer Use / Image Generation は「Not supported / Under development」) |
| Agent Service ネットワーク分離(Standard Setup / BYO VNet 注入) | `Microsoft.App/environments` に委任したサブネット(/27 以上、推奨 /24)へコンテナ注入しエージェントのアウトバウンドを顧客 VNet 内に維持。Standard setup は Storage / AI Search / Cosmos DB の BYO 必須 | GA相当(本文にプレビュー表記なし。ただし関連ページ間で hosted agents の表記揺れあり) | Azure portal+Bicep+Terraform+azd | 対応(azd 拡張、`az provider register` 等) | — | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/virtual-networks | サブネットは Foundry リソースごとに専用。**アウトバウンド設定の後付け・変更は不可(再デプロイ必要)**。リソースと VNet は同一リージョン必須。2026-06-25 以降作成のプロジェクトはプライベート ACR 対応 |
| Managed Virtual Network | Microsoft 管理 VNet でエージェントのアウトバウンドを自動分離。モード: Allow Internet Outbound / Allow Only Approved Outbound(マネージド Azure Firewall 自動作成) | 要確認(ページに preview/GA ラベルなし)。**ポータル UI 未対応**(「There is no Azure Portal UI support to create the managed network yet」) | 未対応(対応予定) | 対応 `az cognitiveservices account managed-network` + `az rest`(API `2026-03-01`)、Bicep/Terraform サンプルあり | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/how-to/managed-virtual-network | 対応リージョン限定(East US, Japan East 他 18 リージョン)。有効化後の無効化不可、BYO VNet からの移行パスなし。`Azure AI Enterprise Network Connection Approver` ロールの割り当てが必要 |
| Customer-Managed Keys (CMK) | Key Vault / Managed HSM の顧客管理キーで保存データを暗号化(プロジェクト成果物、アップロードファイル、評価データ等) | GA相当(プレビュー表記なし。ただし AI Search 基盤の容量制約により**一部リージョンのみ提供**と明記) | Azure portal(作成時ウィザード or Encryption ブレード) | 記載なし(テンプレート言及あり) | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/concepts/encryption-keys-portal | Key Vault は同一リージョン+ソフトデリート/パージ保護必須。MMK→CMK は可、**逆方向(CMK→MMK)は不可**。RSA 2048bit 以上 |

## 接続・IaC

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Connections | 外部リソースへの認証済み接続(リソースレベル/プロジェクトレベル)。シークレットはマネージド Key Vault に保存(BYO Key Vault 接続も可、1リソース1接続) | 機能自体は GA 相当。**接続タイプ別にプレビューあり**: Cosmos DB、Serverless Model、Databricks、SharePoint、Microsoft Fabric、Bing Custom Search、Azure APIM、Model Gateway = プレビュー(いずれも**コード(Bicep)でのみ作成可**) | 新ポータル(Operate > Admin > Connected resources)。classic は Management center | 記載なし | 記載なし(利用は SDK 経由の型あり) | https://learn.microsoft.com/en-us/azure/foundry/how-to/connections-add | モデルデプロイ用のクロスサブスクリプション接続は非対応。BYO Key Vault はシークレット移行非対応(接続の再作成が必要) |
| Bicep / ARM / Terraform デプロイ | `microsoft.cognitiveservices/accounts` + `accounts/projects` のテンプレートデプロイ。Azure portal の Export template (Bicep) 対応。公式サンプル: github.com/microsoft-foundry/foundry-samples | GA | Azure portal (Export template) | 対応 `az deployment` / Azure PowerShell | 対応(管理 SDK) | https://learn.microsoft.com/en-us/azure/foundry/how-to/create-resource-template | Terraform: AzureRM は 4.57.0 超で非破壊更新(kind 変更)、AzAPI も可。ネットワーク注入は作成時のみ設定可(後付け不可) |

## ステータスを横断確認できる公式ページ

| ページ | 内容 | URL |
|---|---|---|
| GA/プレビュー ステータス一覧(最重要) | 新ポータルの GA 宣言と「Feature readiness at GA」表(Home/Discover/Build/Operate の機能別 GA / Preview / Limited preview) | https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability |
| リージョン別 feature availability | プロジェクト作成可能リージョン一覧と機能別リージョン対応。Azure Government の対応/非対応一覧あり。※ Azure Government の Agent Service 対応は専用ページ( https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/azure-government )が最新(Prompt agents 対応 / Workflows プレビュー / Hosted agents 非対応)。region-support 側の「Azure AI Agents 非対応」記載は古い | https://learn.microsoft.com/en-us/azure/foundry/reference/region-support |
| プレビュー機能の管理(無効化) | タグ+カスタム RBAC によるプレビュー抑止方法 | https://learn.microsoft.com/en-us/azure/foundry/how-to/disable-preview-features |
| What's new(月次) | GA/プレビュー開始のトラッキング | https://learn.microsoft.com/en-us/azure/foundry/whats-new-foundry |

## 補足ノート(SI 判断に効く要点)

- **リソースモデルは連続性重視**: 改称・新ポータル化されても ARM 上は `Microsoft.CognitiveServices/accounts` のままで、既存の Azure Policy / RBAC / ネットワーク構成資産がそのまま効く。AOAI からのアップグレードは kind 変更のパッチ操作(非破壊)で、ロールバック手段も提供。
- **ハブベースの終息は「投資停止」段階**: 廃止日は未発表だが、新規投資は Foundry プロジェクトに集中と明言され、classic ドキュメントは NOINDEX・更新周期 365 日。classic 側にしか無いのは **prompt flow(2027-04-20 廃止予定)**・serverless API デプロイ・Azure Language 等で、**マネージドコンピュートは新ポータル側に移った**(2026-07 時点でパブリックプレビュー)。「classic を残さないと機能が足りない」という論拠は年々弱くなっている。
- **表記揺れへの注意**: hosted agents は navigate-from-classic で「GA」、configure-private-link 内では「hosted (preview) agents」と記載が混在。RBAC ロール名も改名ロールアウト中のため、IaC/スクリプトではロール ID(GUID)指定が公式推奨。
- **要確認として残る項目**: (1) Managed VNet のライフサイクルラベル(ページに明記なし・ポータル UI 未対応)、(2) Auto-upgrade プログラム自体のラベル、(3) custom-policy-definition ページの内容(存在のみ確認: https://learn.microsoft.com/en-us/azure/foundry/how-to/custom-policy-definition )。
