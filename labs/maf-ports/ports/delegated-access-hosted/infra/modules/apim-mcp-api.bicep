// APIM の API 1 つ = MCP サーバー 1 つ(方式 A の判定点)。
//
// APIM Consumption は「MCP サーバー」API 型(既存 MCP のパススルー / REST → MCP 変換)に
// 対応しない(ゲートウェイ比較表: Pass-through MCP server = Consumption ❌)。そのため素の
// HTTP API として POST /mcp を 1 本だけ定義し、ステートレス Streamable HTTP(JSON 応答)を
// そのまま中継する。SSE(長時間接続)は Consumption で非対応なので使わない。
//
//   クライアント: https://<apim>.azure-api.net/<path>/mcp
//   バックエンド: <serviceUrl = ツールサーバー/<path>> + /mcp

@description('APIM サービス名(親)')
param apimName string

@description('API 名(= contracts の McpServerSpec.name)')
param apiName string

@description('API の URL サフィックス(= contracts の path から /mcp を除いた部分)')
param apiPath string

@description('バックエンドのベース URL(ENFORCEMENT_MODE=apim のツールサーバー)')
param backendBaseUrl string

@description('API スコープのポリシー XML(infra/apim/policies/<name>.xml を loadTextContent した値)')
param policyXml string

resource apim 'Microsoft.ApiManagement/service@2024-05-01' existing = {
  name: apimName
}

resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'mcp-${apiName}'
  properties: {
    displayName: 'MCP ${apiName}'
    path: apiPath
    protocols: ['https']
    serviceUrl: '${backendBaseUrl}/${apiPath}'
    // 資格情報は Entra の委任トークン(Authorization)だけ。サブスクリプションキーは使わない
    subscriptionRequired: false
    apiType: 'http'
    type: 'http'
  }
}

resource mcpPost 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'mcp-post'
  properties: {
    displayName: 'MCP (streamable HTTP, JSON response)'
    method: 'POST'
    urlTemplate: '/mcp'
  }
}

resource policy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: policyXml
  }
}

output gatewayPath string = '/${apiPath}/mcp'
