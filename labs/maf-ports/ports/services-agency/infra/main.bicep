// services-agency ポートのエージェント固有インフラ。
//
// ARM/Bicep で作る固有リソースは **なし** — 5 役のチャットエージェント+
// 関数ツール(talk_to_* / analyze_project / create_technical_spec)だけで
// 動き、共有基盤(Foundry リソース aif-<baseName> + プロジェクト + モデル
// デプロイ + App Insights)以外に何も要らない。
//
// - Agency Swarm の shared context に相当する共有状態はプロセス内メモリ
//   (ProjectState)。永続化しない設計なので追加ストレージ不要。
// - 通信グラフの発火経路は App Insights のトレースで見る:
//   invoke_agent(送信側)→ execute_tool(talk_to_*)→ invoke_agent(受信側)
//   の入れ子スパンがグラフの実際の通信経路そのものになる。
//
//   az deployment group create -g rg-maf-ports -f main.bicep -p baseName=mafportsw3
//
// 出力はポートの .env に転記する値の再掲(共有基盤のみで動くことの明示)。

@description('共有基盤の baseName(shared.bicep と同じ値)')
param baseName string

// --- 共有基盤(existing 参照)---

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: 'aif-${baseName}'
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundry
  name: 'maf-ports'
}

// --- 出力(ポートの .env に転記する値)---

output openaiV1Endpoint string = 'https://${foundry.properties.customSubDomainName}.openai.azure.com/openai/v1'
output projectEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'
