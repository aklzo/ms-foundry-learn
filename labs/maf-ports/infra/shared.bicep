// 共有基盤: Foundry リソース + プロジェクト + モデルデプロイ + 監視
// 全ポート共通で 1 回だけデプロイする。
//
//   az group create -n rg-maf-ports -l japaneast
//   az deployment group create -g rg-maf-ports -f shared.bicep \
//     -p baseName=mafports modelName=<現行の安価モデル> modelVersion=<版> modelCapacity=10
//
// モデル名・版は docs/survey/features/02-models.md とポータルの現行カタログで確認して渡す
// (リタイアが早いためデフォルト値を置かない)。

@description('リソース名のベース(英小文字数字のみ)')
param baseName string

param location string = resourceGroup().location

@description('デプロイするモデル名(例: gpt-4.1-mini 系の現行安価モデル)')
param modelName string

@description('モデルバージョン文字列')
param modelVersion string

@description('Global Standard の容量(1K TPM 単位)')
param modelCapacity int = 10

// --- 監視(Log Analytics + Application Insights) ---

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${baseName}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${baseName}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// --- Foundry リソース(kind AIServices)+ プロジェクト ---

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'aif-${baseName}'
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'aif-${baseName}'
    allowProjectManagement: true
    publicNetworkAccess: 'Enabled' // ラボ用途。閉域構成は docs/survey/architecture/07 参照
    disableLocalAuth: false
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: 'maf-ports'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'MAF ports lab'
    description: 'awesome-llm-apps を MAF + Foundry に移植する検証ラボ'
  }
}

// プロジェクト → App Insights 接続(トレーシングの送信先)
resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: 'appinsights-${baseName}'
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsights.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsights.id
    }
  }
}

// --- モデルデプロイ(Global Standard・従量) ---

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundry
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}

// --- 出力(ポートの .env に転記する値) ---

output foundryName string = foundry.name
output projectEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'
output openaiV1Endpoint string = 'https://${foundry.properties.customSubDomainName}.openai.azure.com/openai/v1'
output modelDeploymentName string = modelDeployment.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
