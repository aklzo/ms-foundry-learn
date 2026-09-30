// probe 10 専用の最小基盤: Foundry リソース + プロジェクト + 署名中ユーザーの Foundry User。
// hosted agent の版更新と会話の継続だけを見るので、モデル・App Insights は置かない
// (検証用エージェントはモデルを呼ばず、受け取った履歴と自分の版をそのまま返す)。
//
//   az group create -n rg-foundry-probes-p10 -l japaneast
//   az deployment group create -g rg-foundry-probes-p10 -f infra.bicep \
//     -p baseName=<英小文字数字> userObjectId=$(az ad signed-in-user show --query id -o tsv)
//
// App Insights を接続しないので、コンテナに APPLICATIONINSIGHTS_CONNECTION_STRING が
// 注入されないこと(architecture 09 §3.6 の案 3 の前提)も副次的に確認できる。

@description('リソース名のベース(英小文字数字のみ)')
param baseName string

param location string = resourceGroup().location

@description('署名中ユーザーの objectId(hosted agent の作成に Foundry User が要る)')
param userObjectId string

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'aif-${baseName}'
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'aif-${baseName}'
    allowProjectManagement: true
    publicNetworkAccess: 'Enabled' // 検証用途
    disableLocalAuth: false
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: 'probes'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'probe 10: hosted agent version continuity'
  }
}

// hosted agent の作成(agents/write)に要る。サブスクリプション所有者でも自動では付かない
// (2026-09-30 Port 15 で実測。反映まで約 5 分)
var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d' // Foundry User(旧 Azure AI User)

resource userFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, userObjectId, foundryUserRoleId)
  scope: foundry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
    principalId: userObjectId
    principalType: 'User'
  }
}

output projectEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'
