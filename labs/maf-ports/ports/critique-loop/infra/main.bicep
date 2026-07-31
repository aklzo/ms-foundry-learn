// critique-loop ポートのエージェント固有インフラ。
//
// このポートは共有基盤(labs/maf-ports/infra/shared.bicep)のみで動作し、
// 固有 ARM リソースは不要:
// - ループ本体はステートレス(gpt-5.4-mini の呼び出しのみ)
// - クラウド評価(scripts/run_cloud_eval.py)の評価グループ/ランは
//   **プロジェクトのデータプレーンのオブジェクト**で ARM では作れない
//   (travel-memory の Memory ストア・corrective-rag のインデックスと同じ
//   「Bicep → スクリプト」の 2 段デプロイ。tech-selection-guide §2-2)。
//   組み込み評価器(builtin.*)の判定モデルもサービス側でプロビジョニング
//   され、Bicep で管理する対象がない。
// PORTING.md §5 の規約に従い、共有基盤への existing 参照と
// ポートが必要とする出力だけを定義する。
//
//   az deployment group create -g rg-maf-ports -f main.bicep -p baseName=mafports
//
// 評価は Entra ID 認証のみのため、実行者(az login ユーザー)に
// プロジェクトの Azure AI User ロールが必要(共有基盤のデプロイ者なら既定で満たす)。

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
