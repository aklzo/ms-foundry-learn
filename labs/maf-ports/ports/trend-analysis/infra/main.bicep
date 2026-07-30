// trend-analysis ポートのエージェント固有インフラ。
//
// このポートは共有基盤(labs/maf-ports/infra/shared.bicep)のみで動作し、
// 固有リソースは不要(検索はキーレス DuckDuckGo、状態は持たない)。
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
