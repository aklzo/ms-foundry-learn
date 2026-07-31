// db-routing-iq ポートのエージェント固有インフラ。
//
// 固有リソースは Azure AI Search 1 つ(**Basic SKU**)。SKU 選定の実装前調査
// (2026-07 の Learn ドキュメント精読。詳細は README):
//   - agentic retrieval のサービス上限表では Free にも knowledge source /
//     knowledge base 各 3 個の枠があるが、パイプラインが必ず通る**セマンティック
//     ランカー(L2)のスループット表に Free 列が存在せず**、動作保証がない。
//     さらに Free はインデックス 3 個上限(本ポートがちょうど 3 使用)・
//     1 サブスクリプション 1 サービス(Port 4 の Free と衝突)・MI 不可。
//   - **S3 HD は knowledge source / knowledge base = 0(作成不可)** — survey
//     情報の裏取り。
//   - よって現実的な下限は Basic。**Basic は時間課金(約 $0.10/時 ≒ 月 $75
//     規模)**のため、検証後はリソースグループごと削除する前提
//     (knowledge base は scripts/setup_kb.py で再構築できるステートレス設計)。
//
// インデックス/knowledge source/knowledge base はデータプレーン API のため
// ARM/Bicep では書けない(2 段デプロイの定型)→ scripts/setup_kb.py。
// 埋め込みデプロイは不要(本ポートはベクトルなし・テキスト+L2 リランクのみ。
// 設計判断は README)。KB の LLM クエリプランニングは共有基盤のチャット
// デプロイ(FOUNDRY_MODEL)をキー認証で参照する。
//
//   az deployment group create -g rg-maf-ports -f main.bicep -p baseName=mafportsw2
//
// 出力の searchAdminKey は .env(AZURE_SEARCH_ADMIN_KEY)へ転記する。

@description('共有基盤の baseName(shared.bicep と同じ値)')
param baseName string

param location string = resourceGroup().location

@description('AI Search サービス名(グローバル一意。既定: srch-<baseName>-iq)')
param searchServiceName string = 'srch-${baseName}-iq'

// --- 共有基盤(existing 参照)---

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: 'aif-${baseName}'
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundry
  name: 'maf-ports'
}

// --- Azure AI Search(Basic SKU・キー認証)---

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: searchServiceName
  location: location
  sku: { name: 'basic' } // 時間課金に注意(冒頭コメント)。検証後は RG ごと削除
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled' // ラボ用途(閉域構成は docs/survey/architecture/07)
  }
}

// --- 出力(ポートの .env に転記する値)---

output searchName string = search.name
output searchEndpoint string = 'https://${search.name}.search.windows.net'
#disable-next-line outputs-should-not-contain-secrets // ラボ用途の割り切り(本番は RBAC/Key Vault)
output searchAdminKey string = search.listAdminKeys().primaryKey
output openaiV1Endpoint string = 'https://${foundry.properties.customSubDomainName}.openai.azure.com/openai/v1'
output projectEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'
