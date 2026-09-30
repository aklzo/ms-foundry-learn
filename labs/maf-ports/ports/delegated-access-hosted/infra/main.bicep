// delegated-access-hosted ポート(Port 15)のエージェント固有インフラ。
//
// 共有基盤(labs/maf-ports/infra/shared.bicep: Foundry アカウント+プロジェクト+モデル+
// Log Analytics+App Insights)は existing 参照。本テンプレートが作る固有リソース:
//
//   1. ACR(Basic)          … MCP ツールサーバーのイメージ置き場(hosted agent 本体はコード zip の
//                             REMOTE_BUILD なので ACR を使わない)
//   2. ユーザー割り当て MI    … ACR pull と AI Search 読み取り(Search Index Data Reader)。
//                             システム割り当てだと「アプリ作成 → ロール付与 → pull」の順序問題が出るため
//   3. Container Apps 環境+ツールサーバー 2 つ(同じイメージ・ENFORCEMENT_MODE だけ違う)
//        ca-dah-tools-srv  ENFORCEMENT_MODE=server … 方式 B: MCP サーバー自身が JWT とロールを判定。
//                                                   エージェントが直接呼ぶ
//        ca-dah-tools-gw   ENFORCEMENT_MODE=apim   … 方式 A: APIM の裏。宛先・スコープ・ロールは APIM が判定し、
//                                                   サーバーは署名と期限+ゲートウェイ共有シークレットだけ見る
//                                                   (APIM Consumption は VNet 統合できずアプリは外部公開のため、
//                                                   シークレットなしだと公開 URL 直叩きでロール判定を迂回できる)
//      → 2 方式を再デプロイなしで並べて比較できる(どちらを使うかは hosted agent の TOOLS_BASE_URL)
//   4. API Management(Consumption)… 方式 A の判定点。API 3 つ(契約パス)+ validate-jwt ポリシー
//                                    (infra/apim/policies/*.xml)+ Named Value 3 つ(テナント・aud・
//                                    ゲートウェイ共有シークレット)+ App Insights ログ(ヘッダー・本文なし)
//   5. AI Search(Free。1 サブスクリプション 1 つまで → 既にあれば searchSku=basic)
//        … 社内文書の索引。認証はキーと Entra の両方を許可(コンテナは MI、setup_index.py は管理キーでも可)
//
// Entra のアプリ登録・同意・ロール割り当て、Foundry 側のロール(Foundry Agent Consumer+
// UserIdentityImpersonation のカスタムロール)は ARM の外なので scripts/setup_entra.py(既定は dry-run)。
// hosted agent はデータプレーンのオブジェクトなので scripts/deploy_hosted_agent.py(同)。
//
//   # 1 回目: 器(ツールサーバーは quickstart イメージ)
//   az deployment group create -g <rg> -f infra/main.bicep \
//     -p baseName=<shared baseName> toolsApiClientId=<setup_entra.py の出力> apimPublisherEmail=<mail>
//   # 2 回目以降: scripts/deploy_tools_server.sh --apply が ACR ビルド → toolsImage 付きで再デプロイ
//
// 使わない期間は RG ごと削除(APIM は 48 時間ソフトデリート。runbook §8)。

@description('共有基盤の baseName(shared.bicep と同じ値)')
param baseName string

param location string = resourceGroup().location

@description('Entra テナント ID(既定はデプロイ先テナント)')
param tenantId string = tenant().tenantId

@description('ツール API(dah-tools-api)のアプリ(クライアント)ID。scripts/setup_entra.py の出力 TOOLS_API_CLIENT_ID')
param toolsApiClientId string

@description('APIM の発行者メール(Consumption でも必須)')
param apimPublisherEmail string

param apimPublisherName string = 'maf-ports lab'

@description('ツールサーバーのイメージ(<acr>.azurecr.io/dah-tools:<tag>)。空なら quickstart イメージで器だけ作る')
param toolsImage string = ''

@allowed(['free', 'basic'])
@description('AI Search の SKU。Free は 1 サブスクリプション 1 つまで(corrective-rag 等で使用中なら basic)')
param searchSku string = 'free'

@description('社内文書のインデックス名(tools_server/settings.py の既定と同じ)')
param searchIndex string = 'internal-docs'

@secure()
@description('APIM → apim モードのツールサーバーの共有シークレット。deploy_tools_server.sh が既存値を引き継いで渡す(未指定なら毎回新しい値 = 両側同時にローテーション)')
param apimGatewaySecret string = newGuid()

@minValue(0)
@maxValue(1)
@description('ツールサーバーの最小レプリカ。0 = スケールゼロ(APIM Consumption の 30 秒上限にコールドスタートが食い込む場合は 1)')
param toolsMinReplicas int = 0

var suffix = uniqueString(resourceGroup().id)
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
var searchIndexDataReaderRoleId = '1407120a-92aa-4202-b7e9-c0e197c71c8f' // Search Index Data Reader

// contracts.MCP_SERVERS と 1 対 1(name = API 名・ポリシーファイル名 / path = 契約パスから /mcp を除いた部分)。
// tests/test_infra_contracts.py が contracts.py との一致を固定する
var mcpApis = [
  { name: 'docs', path: 'docs' }
  { name: 'suppliers', path: 'suppliers' }
  { name: 'supplier-admin', path: 'supplier-admin' }
]

// --- 共有基盤(existing 参照)---

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: 'aif-${baseName}'
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundry
  name: 'maf-ports'
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: 'log-${baseName}'
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: 'appi-${baseName}'
}

// --- ID とイメージ置き場 ---

resource toolsIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-dah-tools-${baseName}'
  location: location
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'crdah${suffix}'
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false // pull は MI、push は az acr build(ARM 権限)
  }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, toolsIdentity.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: toolsIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- 社内文書の索引(AI Search)---

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: 'srch-dah-${suffix}'
  location: location
  sku: { name: searchSku }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled' // ラボ用途(閉域構成は docs/survey/architecture/07)
    // 既定はキー認証のみ。Entra(RBAC)も受けるには aadOrApiKey を明示する(Free でも可)
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
  }
}

resource searchReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, toolsIdentity.id, searchIndexDataReaderRoleId)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReaderRoleId)
    principalId: toolsIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- MCP ツールサーバー(Container Apps・同じイメージを 2 モードで)---

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-dah-${baseName}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// 同じイメージ・同じ設定で ENFORCEMENT_MODE だけ変える(module の params はオブジェクトリテラル必須のため 2 回書く)
var searchEndpoint = 'https://${search.name}.search.windows.net'

module toolsServer 'modules/tools-app.bicep' = {
  name: 'dah-tools-server'
  params: {
    name: 'ca-dah-tools-srv'
    enforcementMode: 'server'
    location: location
    environmentId: containerEnv.id
    image: toolsImage
    acrLoginServer: acr.properties.loginServer
    identityId: toolsIdentity.id
    identityClientId: toolsIdentity.properties.clientId
    tenantId: tenantId
    toolsApiClientId: toolsApiClientId
    searchEndpoint: searchEndpoint
    searchIndex: searchIndex
    minReplicas: toolsMinReplicas
  }
  dependsOn: [acrPull, searchReader]
}

module toolsGateway 'modules/tools-app.bicep' = {
  name: 'dah-tools-gateway-backend'
  params: {
    name: 'ca-dah-tools-gw'
    enforcementMode: 'apim'
    gatewaySecret: apimGatewaySecret
    location: location
    environmentId: containerEnv.id
    image: toolsImage
    acrLoginServer: acr.properties.loginServer
    identityId: toolsIdentity.id
    identityClientId: toolsIdentity.properties.clientId
    tenantId: tenantId
    toolsApiClientId: toolsApiClientId
    searchEndpoint: searchEndpoint
    searchIndex: searchIndex
    minReplicas: toolsMinReplicas
  }
  dependsOn: [acrPull, searchReader]
}

// --- 方式 A の判定点(APIM Consumption)---

module apim 'modules/apim.bicep' = {
  name: 'dah-apim'
  params: {
    name: 'apim-dah-${suffix}'
    location: location
    publisherEmail: apimPublisherEmail
    publisherName: apimPublisherName
    tenantId: tenantId
    toolsApiClientId: toolsApiClientId
    gatewaySecret: apimGatewaySecret
    backendBaseUrl: toolsGateway.outputs.url
    appInsightsId: appInsights.id
    appInsightsConnectionString: appInsights.properties.ConnectionString
    mcpApis: mcpApis
  }
}

// --- 出力(.env と deploy スクリプトが使う値)---

output acrName string = acr.name
output apimName string = apim.outputs.name
output acrLoginServer string = acr.properties.loginServer
@description('方式 A の TOOLS_BASE_URL(MCP URL = これ + /docs/mcp 等)')
output apimGatewayUrl string = apim.outputs.gatewayUrl
@description('方式 B の TOOLS_BASE_URL(ENFORCEMENT_MODE=server のツールサーバー)')
output toolsServerUrl string = toolsServer.outputs.url
@description('APIM 裏のツールサーバーの直 URL(迂回テスト用。エージェントには渡さない)')
output toolsGatewayBackendUrl string = toolsGateway.outputs.url
output toolsServerAppName string = toolsServer.outputs.name
output toolsGatewayAppName string = toolsGateway.outputs.name
output searchName string = search.name
output searchEndpoint string = searchEndpoint
output searchIndex string = searchIndex
output toolsIdentityClientId string = toolsIdentity.properties.clientId
output foundryName string = foundry.name
@description('Foundry Agent Consumer / カスタムロールの割り当てスコープ(setup_entra.py --role-scope project)')
output projectResourceId string = project.id
output projectEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'
