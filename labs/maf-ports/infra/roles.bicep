// 第2段: MI へのロール割り当て(shared.bicep デプロイ後に実行)
// principalId はパラメータで受ける(ARM 制約により割り当て名に実行時値が
// 使えないため。pid を guid シードに含めることで MI ローテーション時も
// 新しい割り当てが作られ、孤児温存を防ぐ)。

@description('リソース名のベース(shared.bicep と同じ値)')
param baseName string

@description('Foundry アカウントのシステム割り当て MI の principalId')
param accountPrincipalId string

@description('プロジェクトのシステム割り当て MI の principalId')
param projectPrincipalId string

var openaiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User
var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d' // Foundry User (旧 Azure AI User)

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: 'aif-${baseName}'
}

resource assignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for pair in [
    { pid: projectPrincipalId, role: openaiUserRoleId }
    { pid: projectPrincipalId, role: foundryUserRoleId }
    { pid: accountPrincipalId, role: openaiUserRoleId }
    { pid: accountPrincipalId, role: foundryUserRoleId }
  ]: {
    name: guid(foundry.id, pair.pid, pair.role)
    scope: foundry
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', pair.role)
      principalId: pair.pid
      principalType: 'ServicePrincipal'
    }
  }
]
