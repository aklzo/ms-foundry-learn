// travel-memory ポートのエージェント固有インフラ。
//
// 固有の ARM リソースは **なし**。理由:
//   - Memory ストアはプロジェクトの**データプレーン API**(/memory_stores)で
//     作るため ARM/Bicep では書けない → scripts/setup_memory.py に分離
//     (corrective-rag のインデックス作成と同じ「2 段デプロイ」構成)。
//   - ストア構成に使うモデルはデプロイ済み: チャット gpt-5.4-mini は共有基盤
//     (shared.bicep)、埋め込み text-embedding-3-small は corrective-rag の
//     main.bicep が共有 Foundry アカウントへ追加済み。
//   - Memory は**パブリックプレビュー**。共有基盤は Japan East(Memory の
//     対応 19 リージョンに含まれる)。VNet 統合は非対応(README 参照)。
//
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
