// corrective-rag ポートのエージェント固有インフラ。
//
// 固有リソース(PORTING.md §5: 共有基盤は existing 参照、固有分のみ定義):
//   1. Azure AI Search — 元アプリの Qdrant の置き換え。**Free SKU**(コスト
//      最小)。Free の制約: インデックス 3 個・ストレージ 50MB・レプリカ/
//      パーティション拡張不可・SLA なし・**セマンティックランカー不可**。
//      本番想定では Basic 以上+セマンティックランカーが定石(README の学び
//      参照)。Free は 1 サブスクリプション 1 サービスまでの点にも注意。
//   2. text-embedding-3-small のモデルデプロイ — クライアント側埋め込み用に
//      共有 Foundry アカウントへ追加(integrated vectorization は採用しない。
//      設計判断は README)。共有 shared.bicep は chat モデルのみ持つため、
//      埋め込みデプロイは本ポートの責務とする。
//
//   az deployment group create -g rg-maf-ports -f main.bicep -p baseName=mafports
//
// 出力の searchAdminKey は .env(AZURE_SEARCH_ADMIN_KEY)へ転記する。

@description('共有基盤の baseName(shared.bicep と同じ値)')
param baseName string

param location string = resourceGroup().location

@description('AI Search サービス名(グローバル一意。既定: srch-<baseName>)')
param searchServiceName string = 'srch-${baseName}'

@description('埋め込みモデル名')
param embeddingModelName string = 'text-embedding-3-small'

@description('埋め込みモデルのバージョン')
param embeddingModelVersion string = '1'

@description('埋め込みデプロイの容量(1K TPM 単位)')
param embeddingCapacity int = 10

// --- 共有基盤(existing 参照)---

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: 'aif-${baseName}'
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundry
  name: 'maf-ports'
}

// --- Azure AI Search(Free SKU・キー認証)---

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: searchServiceName
  location: location
  sku: { name: 'free' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled' // ラボ用途(閉域構成は docs/survey/architecture/07)
  }
}

// --- 埋め込みモデルデプロイ(共有 Foundry アカウントへ追加)---

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundry
  name: embeddingModelName
  sku: {
    name: 'GlobalStandard'
    capacity: embeddingCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: embeddingModelVersion
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}

// --- 出力(ポートの .env に転記する値)---

output searchName string = search.name
output searchEndpoint string = 'https://${search.name}.search.windows.net'
#disable-next-line outputs-should-not-contain-secrets // ラボ用途の割り切り(本番は RBAC/Key Vault)
output searchAdminKey string = search.listAdminKeys().primaryKey
output embeddingDeploymentName string = embeddingDeployment.name
output openaiV1Endpoint string = 'https://${foundry.properties.customSubDomainName}.openai.azure.com/openai/v1'
output projectEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'
