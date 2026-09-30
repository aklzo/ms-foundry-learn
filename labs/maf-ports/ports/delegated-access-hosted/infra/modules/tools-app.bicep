// MCP ツールサーバー(3 エンドポイントを 1 アプリに mount)の Container App 1 つ分。
// main.bicep から ENFORCEMENT_MODE 違いで 2 回呼ぶ(server = 方式 B / apim = 方式 A の APIM 裏)。
//
// - イメージ未指定(toolsImage = '')のときは quickstart イメージ(:80 で待ち受け)で「器」だけ作る。
//   scripts/deploy_tools_server.sh が ACR にビルドしたイメージ名を渡して再デプロイする
// - 取引先マスタはプロセス内メモリ(更新はレプリカごと・再起動で消える)なので maxReplicas は 1 に固定
// - AI Search はユーザー割り当て MI(AZURE_CLIENT_ID で DefaultAzureCredential に選ばせる)
// - apim モードのアプリにだけゲートウェイ共有シークレット(APIM_GATEWAY_SECRET)を Container Apps の
//   secret として渡す。APIM は同じ値を Named Value dah-gateway-secret から x-apim-gateway-secret
//   ヘッダーで送り、サーバーは一致しない要求を拒否する(= Container Apps の公開 URL を直接叩いて
//   APIM のロール判定を迂回する経路を塞ぐ)

@description('Container App 名(32 文字以内・英小文字数字とハイフン)')
param name string

param location string

@description('Container Apps 環境のリソース ID')
param environmentId string

@description('ツールサーバーのイメージ(空なら quickstart イメージで器だけ作る)')
param image string

@description('ACR のログインサーバー(例: crdahxxxx.azurecr.io)')
param acrLoginServer string

@description('ACR pull と AI Search 読み取りに使うユーザー割り当て MI のリソース ID')
param identityId string

@description('同 MI のクライアント ID(コンテナの AZURE_CLIENT_ID)')
param identityClientId string

@allowed(['server', 'apim'])
@description('最終判定の置き場所(contracts.EnforcementMode)')
param enforcementMode string

param tenantId string
param toolsApiClientId string
param searchEndpoint string
param searchIndex string

@secure()
@description('APIM → ツールサーバーの共有シークレット(apim モードで必須。server モードでは使わない)')
param gatewaySecret string = ''

@description('ツールサーバーの待ち受けポート(tools_server/settings.py の既定 8080)')
param toolsPort int = 8080

@minValue(0)
@maxValue(1)
@description('最小レプリカ数。0 = スケールゼロ(コールドスタートあり)')
param minReplicas int = 0

var bootstrap = empty(image)
var effectiveImage = bootstrap ? 'mcr.microsoft.com/k8se/quickstart:latest' : image
var targetPort = bootstrap ? 80 : toolsPort
var usesGatewaySecret = enforcementMode == 'apim'
var baseEnv = [
  { name: 'ENFORCEMENT_MODE', value: enforcementMode }
  { name: 'ENTRA_TENANT_ID', value: tenantId }
  { name: 'TOOLS_API_CLIENT_ID', value: toolsApiClientId }
  { name: 'SEARCH_ENDPOINT', value: searchEndpoint }
  { name: 'SEARCH_INDEX', value: searchIndex }
  { name: 'AZURE_CLIENT_ID', value: identityClientId }
  { name: 'PORT', value: string(toolsPort) }
]
// 値は Container Apps の secret に置き、環境変数は secretRef で参照する(テンプレートの出力やリビジョンの
// 環境変数一覧に平文で出さない)
var gatewayEnv = usesGatewaySecret ? [{ name: 'APIM_GATEWAY_SECRET', secretRef: 'apim-gateway-secret' }] : []

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        // APIM Consumption は VNet 統合できないため、APIM 裏のアプリも外部公開になる(README「方式 A の迂回」)
        external: true
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      }
      secrets: usesGatewaySecret ? [{ name: 'apim-gateway-secret', value: gatewaySecret }] : []
      // quickstart イメージは MCR の公開イメージなので、レジストリ設定は自前イメージのときだけ付ける
      registries: bootstrap ? [] : [
        {
          server: acrLoginServer
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'tools'
          image: effectiveImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: concat(baseEnv, gatewayEnv)
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 1
      }
    }
  }
}

output name string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn
output url string = 'https://${app.properties.configuration.ingress.fqdn}'
