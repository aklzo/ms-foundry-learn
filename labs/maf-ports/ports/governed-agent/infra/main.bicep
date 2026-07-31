// governed-agent ポートのエージェント固有インフラ。
//
// ARM/Bicep で作る固有リソースは **なし** — ガバナンス層(ポリシー強制・
// 信頼ゲート・ハッシュ連鎖監査)はすべてアプリ内の MAF middleware であり、
// 共有基盤(Foundry リソース+モデルデプロイ+App Insights)だけで動く。
//
// サービス層の対応物メモ(docs/survey/features/06-safety-guardrails.md):
// - Foundry の「エージェント向けガードレール」(プレビュー)は Tool call /
//   Tool response の介入ポイントを持ち、本ポートのポリシー middleware と
//   守備範囲が重なる。ただし ARM 上の実体は RAI policy
//   (Microsoft.CognitiveServices/accounts/raiPolicies)で、コントロールの
//   構成は新ポータル(Build > Guardrails)/ REST が主サーフェス。
//   決定論の業務ルール(金額上限・営業時間)はガードレールでは表現できず、
//   アプリ層に残る。**本ポートではガードレールの実機検証はスコープ外**
//   (README の対比表参照)。
//
//   az deployment group create -g rg-maf-ports -f main.bicep -p baseName=<shared baseName>
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
