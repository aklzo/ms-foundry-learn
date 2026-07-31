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

// --- RBAC はここに置かない(roles.bicep で第2段デプロイ) ---
// 理由(W2 で実測した罠):
// 1. サービス側機能(Memory / クラウド評価)はプロジェクト・アカウント MI に
//    モデルデータプレーン権限(Cognitive Services OpenAI User)と
//    Foundry User が必要(ポータル作成では自動、Bicep 作成では手動)
// 2. プロジェクトの再デプロイで MI がローテーションすることがあり、
//    このテンプレート内で id 固定名の割り当てを作ると「名前一致で既存扱い
//    →旧 principal への孤児割り当てが残る」(PermissionDenied の温床)
// 3. ARM の制約でロール割り当て名に実行時値(principalId)は使えない
// → principalId をパラメータで渡す roles.bicep を分離し、
//   本テンプレートのデプロイ後に必ず実行する:
//     PID=$(az rest --method get --url "https://management.azure.com$(az cognitiveservices account show -n aif-<baseName> -g <rg> --query id -o tsv)/projects/<project>?api-version=2025-06-01" --query identity.principalId -o tsv)
//     AID=$(az cognitiveservices account show -n aif-<baseName> -g <rg> --query identity.principalId -o tsv)
//     az deployment group create -g <rg> -f roles.bicep -p baseName=<baseName> accountPrincipalId=$AID projectPrincipalId=$PID

// --- 出力(ポートの .env に転記する値) ---

output foundryName string = foundry.name
output projectEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'
output openaiV1Endpoint string = 'https://${foundry.properties.customSubDomainName}.openai.azure.com/openai/v1'
output modelDeploymentName string = modelDeployment.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
