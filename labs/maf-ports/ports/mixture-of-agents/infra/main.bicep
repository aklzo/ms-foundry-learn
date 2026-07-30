// mixture-of-agents ポートのエージェント固有インフラ。
//
// このポートは共有基盤(labs/maf-ports/infra/shared.bicep)のみで動作し、
// 固有リソースは不要(既定は gpt-5.4-mini ×ペルソナ4体の self-MoA、状態なし)。
// モデル多様性モード(FOUNDRY_PROPOSER_MODELS)を使う場合は、共有基盤側に
// 追加のモデルデプロイ(Microsoft.CognitiveServices/accounts/deployments)が
// 必要になる — それはポート固有でなく共有基盤の変更なので、ここには置かない。
// PORTING.md §5 の規約に従い、共有基盤への existing 参照と
// ポートが必要とする出力だけを定義する。
//
//   az deployment group create -g rg-maf-ports -f main.bicep -p baseName=mafports

@description('共有基盤の baseName(shared.bicep と同じ値)')
param baseName string

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: 'aif-${baseName}'
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundry
  name: 'maf-ports'
}

output openaiV1Endpoint string = 'https://${foundry.properties.customSubDomainName}.openai.azure.com/openai/v1'
output projectEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'
