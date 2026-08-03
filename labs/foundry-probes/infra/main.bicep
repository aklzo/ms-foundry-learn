// foundry-probes 基盤: Foundry リソース + プロジェクト + モデル + 監視 + 署名中ユーザー RBAC
// maf-ports/infra/shared.bicep を土台に、probe 用に以下を変更:
//   - 署名中ユーザーへのデータプレーンロール割り当てを同梱(userObjectId param)
//   - model router デプロイを条件付きで追加(deployRouter=true のとき)
//
//   az group create -n rg-foundry-probes -l japaneast
//   az deployment group create -g rg-foundry-probes -f main.bicep \
//     -p baseName=fprobes modelName=<現行の安価モデル> modelVersion=<版> \
//        userObjectId=$(az ad signed-in-user show --query id -o tsv)
//
// MI(アカウント/プロジェクト)へのロールは maf-ports と同じ罠(principalId の
// ローテーション)があるため roles.bicep で第2段デプロイする。

@description('リソース名のベース(英小文字数字のみ)')
param baseName string

param location string = resourceGroup().location

@description('デプロイするモデル名(02-models.md で現行の安価 GA モデルを確認)')
param modelName string

@description('モデルバージョン文字列')
param modelVersion string

@description('Global Standard の容量(1K TPM 単位)')
param modelCapacity int = 10

@description('署名中ユーザーの objectId(データプレーンロールを割り当てる)')
param userObjectId string

@description('model router もデプロイするか')
param deployRouter bool = false

@description('model router のバージョン(deployRouter=true のとき必須)')
param routerVersion string = ''

// --- 監視(Log Analytics + Application Insights。継続評価・トレース確認用) ---

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
    publicNetworkAccess: 'Enabled' // ラボ用途
    disableLocalAuth: false
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: 'probes'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Foundry feature probes'
    description: 'maf-ports で未検証の Foundry 機能を単純例で挙動確認するラボ'
  }
}

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
  // アカウント配下のサブリソース操作は直列のみ(並走すると RequestConflict)。
  // プロジェクト作成完了後にモデルデプロイを開始する。
  dependsOn: [project]
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

resource routerDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = if (deployRouter) {
  parent: foundry
  name: 'model-router'
  dependsOn: [modelDeployment] // デプロイの直列化(同時作成は Conflict になることがある)
  sku: {
    name: 'GlobalStandard'
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'model-router'
      version: routerVersion
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}

// --- 署名中ユーザーへのデータプレーンロール ---
// maf-ports W1/W2 の知見: Bicep 作成ではポータルと違いロールが自動付与されない。
// ユーザー objectId はローテーションしないので main.bicep 同梱で安全。

var openaiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User
var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d' // Foundry User

resource userRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for role in [openaiUserRoleId, foundryUserRoleId]: {
    name: guid(foundry.id, userObjectId, role)
    scope: foundry
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role)
      principalId: userObjectId
      principalType: 'User'
    }
  }
]

// --- 出力(.env に転記する値) ---

output foundryName string = foundry.name
output projectEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'
output openaiV1Endpoint string = 'https://${foundry.properties.customSubDomainName}.openai.azure.com/openai/v1'
output modelDeploymentName string = modelDeployment.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
