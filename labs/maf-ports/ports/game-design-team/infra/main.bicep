// game-design-team ポートのエージェント固有インフラ。
//
// このポートは共有基盤(labs/maf-ports/infra/shared.bicep)のみで動作し、
// 固有リソースは不要(gpt-5.4-mini 1 デプロイを 4 役割で共用、外部ツール
// なし、状態なし — 共有 context はプロセス内のメッセージとして運ぶ)。
// PORTING.md §5 の規約に従い、共有基盤への existing 参照とポートが必要と
// する出力だけを定義する。
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
