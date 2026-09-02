// cu-video-rag 基盤: Foundry リソース(CU + Speech TTS + モデルデプロイ)+ Storage + AI Search
// foundry-probes/infra/main.bicep を土台に CU 検証用へ変更:
//   - CU は Foundry リソース(kind AIServices)の /contentunderstanding データプレーンで動く
//     (プロジェクト不要)。モデルデプロイ(補完+埋め込み)を defaults に紐づける必要が
//     あるため両方をデプロイする
//   - TTS(ja-JP)・CU・SAS はラボ簡略化のためキー認証を使う(顧客環境なら Entra 必須。
//     helpdesk 規約との差は README に明記)
//
//   az group create -n rg-cu-video-rag -l japaneast
//   az deployment group create -g rg-cu-video-rag -f main.bicep \
//     -p baseName=cuvrag userObjectId=$(az ad signed-in-user show --query id -o tsv)

@description('リソース名のベース(英小文字数字のみ)')
param baseName string

param location string = resourceGroup().location

@description('CU の生成フィールド・セグメント記述に使う補完モデル')
param completionModel string = 'gpt-5.4-mini'
param completionVersion string = '2026-03-17'

@description('ハイブリッド検索と CU defaults 用の埋め込みモデル')
param embeddingModel string = 'text-embedding-3-small'
param embeddingVersion string = '1'

@description('ragas の判定用モデル(温度 0 指定可能な非 reasoning 系)')
param judgeModel string = 'gpt-4.1-mini'
param judgeVersion string = '2025-04-14'

@description('署名中ユーザーの objectId(データプレーンロールを割り当てる)')
param userObjectId string

var suffix = uniqueString(resourceGroup().id)

// --- Foundry リソース(kind AIServices。CU / Speech / AOAI を包含) ---

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'aif-${baseName}'
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'aif-${baseName}-${suffix}'
    publicNetworkAccess: 'Enabled'
    // ラボ簡略化: キー認証を有効のまま(TTS/CU/defaults PATCH をキーで叩く)
  }
}

@batchSize(1) // アカウント配下のデプロイは直列(probes と同じ RequestConflict 回避)
resource deployments 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [
  for d in [
    // 動画解析はセグメントごとに視覚+生成でトークンを食う。50K TPM では並行解析で
    // 429 になった実測(findings 1-6)があるため 200K を既定にする
    { name: completionModel, model: completionModel, version: completionVersion, capacity: 200 }
    { name: embeddingModel, model: embeddingModel, version: embeddingVersion, capacity: 120 }
    { name: judgeModel, model: judgeModel, version: judgeVersion, capacity: 100 }
  ]: {
    parent: foundry
    name: d.name
    sku: { name: 'GlobalStandard', capacity: d.capacity }
    properties: {
      model: { format: 'OpenAI', name: d.model, version: d.version }
      versionUpgradeOption: 'OnceCurrentVersionExpired'
    }
  }
]

// --- 動画置き場(CU へは SAS URL で渡す = quickstart の URL 入力方式) ---

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: toLower(replace('${baseName}st${suffix}', '-', ''))
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }

  resource blob 'blobServices' = {
    name: 'default'
    resource videos 'containers' = {
      name: 'videos'
    }
  }
}

// --- ハイブリッド検索(BM25 ja + ベクトル) ---

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: 'srch-${baseName}-${suffix}'
  location: location
  sku: { name: 'basic' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    authOptions: { aadOrApiKey: { aadAuthFailureMode: 'http401WithBearerChallenge' } }
  }
}

// --- 署名中ユーザーへのデータプレーンロール(probes と同じく main に同梱) ---

var roles = [
  '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User (embeddings)
  'a97b65f3-24c7-4388-baec-2e87135dc908' // Cognitive Services User (CU / Speech を Entra で叩く場合用)
]

resource userAiRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for roleId in roles: {
    name: guid(userObjectId, foundry.id, roleId)
    scope: foundry
    properties: {
      principalId: userObjectId
      principalType: 'User'
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
    }
  }
]

resource userBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(userObjectId, storage.id, 'blob-contrib')
  scope: storage
  properties: {
    principalId: userObjectId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // Storage Blob Data Contributor
    )
  }
}

output foundryName string = foundry.name
output foundryEndpoint string = foundry.properties.endpoint
output aoaiEndpoint string = 'https://${foundry.properties.customSubDomainName}.cognitiveservices.azure.com'
output storageName string = storage.name
output searchName string = search.name
output searchEndpoint string = 'https://${search.name}.search.windows.net'
