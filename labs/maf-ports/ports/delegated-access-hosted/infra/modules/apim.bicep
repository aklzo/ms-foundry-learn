// 方式 A の判定点: API Management(Consumption)+ MCP サーバー 3 つ分の API + validate-jwt ポリシー。
//
// Consumption を選んだ理由と制約(2026-09-30 に Learn で確認。README「方式 A と B の比較」):
// - validate-jwt は全ゲートウェイ(classic / v2 / consumption / self-hosted / workspace)で使える
// - 従量課金・スケールは自動。ただし 1 リクエストの総所要時間は 30 秒まで、ポリシー文書は 16 KiB まで
// - 長時間接続(SSE)は非対応 → MCP はステートレス Streamable HTTP + JSON 応答で中継する
// - 「MCP サーバー」API 型・rate-limit-by-key・VNet 統合・静的 IP・Azure Monitor のリクエストログは非対応
//   (ゲートウェイのログは Application Insights 連携のみ)
// - 削除すると 48 時間ソフトデリート(同名で作り直すなら az apim deletedservice purge)

param name string
param location string

@description('発行者メール(Consumption でも必須)')
param publisherEmail string
param publisherName string

@description('Entra テナント ID(ポリシーの Named Value dah-tenant-id)')
param tenantId string

@description('ツール API のクライアント ID(ポリシーの Named Value dah-tools-api-client-id = トークンの aud)')
param toolsApiClientId string

@secure()
@description('ゲートウェイ共有シークレット(Named Value dah-gateway-secret。ポリシーが x-apim-gateway-secret で送る)')
param gatewaySecret string

@description('ENFORCEMENT_MODE=apim のツールサーバーのベース URL')
param backendBaseUrl string

@description('共有基盤の Application Insights のリソース ID')
param appInsightsId string

@secure()
@description('同 接続文字列(ゲートウェイのリクエストログの送り先)')
param appInsightsConnectionString string

@description('MCP API の一覧 [{ name, path }](contracts.MCP_SERVERS と一致。tests/test_infra_contracts.py が固定)')
param mcpApis array

// ポリシー XML(R 担当の infra/apim/policies/*.xml)。loadTextContent はリテラルパスしか取れないので列挙する。
// オフラインでは tools_server/apim_emulator.py が同じファイルを読んで判定を再現する
var policies = {
  docs: loadTextContent('../apim/policies/docs.xml')
  suppliers: loadTextContent('../apim/policies/suppliers.xml')
  'supplier-admin': loadTextContent('../apim/policies/supplier-admin.xml')
}

resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: name
  location: location
  sku: {
    name: 'Consumption'
    capacity: 0
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

// ポリシーの {{dah-tenant-id}} / {{dah-tools-api-client-id}} / {{dah-gateway-secret}} を APIM が解決する
resource nvTenant 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: 'dah-tenant-id'
  properties: {
    displayName: 'dah-tenant-id'
    value: tenantId
    secret: false
  }
}

resource nvToolsAud 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: 'dah-tools-api-client-id'
  properties: {
    displayName: 'dah-tools-api-client-id'
    value: toolsApiClientId
    secret: false
  }
}

// APIM を迂回した直接呼び出しを apim モードのサーバーが拒否するための共有シークレット(secret 扱い)
resource nvGatewaySecret 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: 'dah-gateway-secret'
  properties: {
    displayName: 'dah-gateway-secret'
    value: gatewaySecret
    secret: true
  }
}

// ゲートウェイのリクエストログ → Application Insights(Consumption で使える唯一のリクエストログ経路)。
// ヘッダーと本文は記録しない(Authorization = 委任トークンとゲートウェイ共有シークレットをログに残さない。本文ログは MCP の
// 応答をバッファリングさせる原因にもなる)
resource logger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = {
  parent: apim
  name: 'appinsights'
  properties: {
    loggerType: 'applicationInsights'
    resourceId: appInsightsId
    credentials: {
      connectionString: appInsightsConnectionString
    }
  }
}

var noPayload = {
  headers: []
  body: {
    bytes: 0
  }
}

resource diagnostics 'Microsoft.ApiManagement/service/diagnostics@2024-05-01' = {
  parent: apim
  name: 'applicationinsights'
  properties: {
    loggerId: logger.id
    alwaysLog: 'allErrors'
    httpCorrelationProtocol: 'W3C'
    verbosity: 'information'
    logClientIp: true
    sampling: {
      samplingType: 'fixed'
      percentage: 100
    }
    frontend: {
      request: noPayload
      response: noPayload
    }
    backend: {
      request: noPayload
      response: noPayload
    }
  }
}

module mcpApi 'apim-mcp-api.bicep' = [
  for api in mcpApis: {
    name: 'apim-mcp-${api.name}'
    params: {
      apimName: apim.name
      apiName: api.name
      apiPath: api.path
      backendBaseUrl: backendBaseUrl
      policyXml: policies[api.name]
    }
    // ポリシーが参照する Named Value を先に作る(無いとポリシーの保存が失敗する)
    dependsOn: [
      nvTenant
      nvToolsAud
      nvGatewaySecret
    ]
  }
]

output name string = apim.name
output gatewayUrl string = apim.properties.gatewayUrl
