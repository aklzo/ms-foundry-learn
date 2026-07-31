// hn-briefing-hosted ポートのエージェント固有インフラ。
//
// ARM/Bicep で作る固有リソースは **なし** — 本ポートの固有物は
//   1. hosted agent(エージェント定義+バージョン+コード zip)
//   2. Routine(schedule トリガー)
// のいずれも**データプレーンのオブジェクト**で、ARM のリソース型が存在しない
// (実装前調査 2026-07: quickstart-hosted-agent / concepts/hosted-agents /
// how-to/use-routines のデプロイ手段は azd 拡張・SDK create_version_from_code・
// ポータル・REST のみ。azd の azure.yaml `infra.provider: microsoft.foundry` も
// azd 独自のプロビジョニングであってユーザー Bicep ではない)。
// → AI Search インデックスや Memory ストアと同じ「Bicep → セットアップ
//   スクリプト」の 2 段デプロイ定型(tech-selection-guide §2-2)がここでも成立:
//     az deployment group create(共有基盤 shared.bicep のみ)
//       → hosting/deploy_hosted_agent.py(hosted agent 版)
//       → scripts/setup_routine.py(Routine)
//
// 未確定点(ライブで検証): コードデプロイ(REMOTE_BUILD)のコンテナイメージ
// 格納先。azd フローはプロジェクト用 Container Registry をプロビジョニング
// するが、SDK 経路の quickstart は ACR 事前作成に言及しない(サービス管理
// ストレージの可能性)。SDK 経路が ACR 不在で失敗する場合は azd フローへ
// 切替える(README の残リスク参照)。
//
// リージョン適合(実装前調査): hosted agents は 31 リージョン、Routines
// (プレビュー)は 8 リージョンで、**どちらも Japan East を含む** — 共有基盤
// (japaneast)のままで両機能を使える。
//
//   az deployment group create -g rg-maf-ports -f main.bicep -p baseName=mafportsw2
//
// 出力はスクリプトが使う .env 値の再掲(共有基盤のみで動くことの明示)。

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
