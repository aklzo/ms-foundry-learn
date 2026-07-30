// github-mcp ポートのエージェント固有インフラ。
//
// 固有の ARM リソースは **なし**。理由:
//   - MCP は**クライアント側(MAF)からのアウトバウンド接続**であり、Azure 側に
//     追加リソースを要しない。接続先の GitHub 公式リモート MCP サーバー
//     (https://api.githubcopilot.com/mcp/)は GitHub がホストし、認証は PAT を
//     クライアントが Authorization: Bearer ヘッダーで付与する(PAT は環境変数
//     GITHUB_TOKEN — Azure 側にシークレットを置かないラボ構成)。
//   - 元アプリの Docker(ghcr.io/github/github-mcp-server の stdio 起動)も
//     リモート化で不要になり、インフラ差分はゼロになる。
//   - 対比: Foundry Agent Service の MCP ツール(GA)を使う場合は**サーバー側**
//     (エージェント定義+プロジェクト接続)に MCP 接続を構成するが、本ポートは
//     MAF クライアント経路の検証が目的(README の学び参照)。
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
