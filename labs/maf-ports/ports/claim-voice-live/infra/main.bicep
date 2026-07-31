// claim-voice-live ポートのエージェント固有インフラ。
//
// ARM/Bicep で作る固有リソースは **なし** — Voice Live API は共有基盤の
// Foundry リソース(aif-<baseName>)だけで使える。実装前調査(2026-07、
// Learn: voice-live / voice-live-quickstart / regions?tabs=voice-live)の裏取り:
//
// 1. **モデルはマネージド提供**: overview 原文 "All natively supported models
//    are fully managed, so you don't need to deploy models, worry about
//    capacity planning, or provision throughput." — survey features/07 の
//    「モデルはマネージド提供」の記述を一次情報で確認。よって
//    **リアルタイム/音声用モデルのデプロイ追加は不要**(shared.bicep の
//    チャットモデルデプロイとは独立)。
//    例外: gpt-5.5 / gpt-5.4-mini / gpt-5.4-nano は pre-deploy されず
//    BYOM(自リソースへのデプロイ+接続)が必要 — 本ポートは使わない。
// 2. **リージョン**: Voice Live は Japan East 対応。ただしモデル別に提供が
//    異なり、**gpt-realtime 系(ネイティブ音声)と azure-realtime は
//    Japan East 非提供**。gpt-4o / gpt-4.1 / gpt-5 系(音声入出力を Azure
//    Speech の STT/TTS が担う構成)は Global standard で利用可 → 既定
//    モデルは gpt-4.1-mini(Voice Live basic 価格帯。config.py)。
// 3. **エンドポイント**: wss://<custom-domain>.services.ai.azure.com/
//    voice-live/realtime?api-version=2026-04-10&model=<model>(安定版 API)。
//    ARM リソースとしては共有基盤の AIServices アカウントそのもの。
// 4. **認証**: api-key(共有基盤の FOUNDRY_API_KEY がそのまま使える)または
//    Entra(scope https://ai.azure.com/.default)。Entra 経路はユーザー/MI に
//    Cognitive Services User + Foundry User ロールが必要(キー認証を使う本
//    ラボの既定では RBAC 追加不要)。
//
// → 「Bicep → セットアップスクリプト」の 2 段デプロイ定型すら不要で、
//   共有基盤のみで動く(データプレーンのセッションが全て)。
//
//   az deployment group create -g rg-maf-ports -f main.bicep -p baseName=mafportsw2
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
output voiceLiveEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/'
output voiceLiveWebSocketUrl string = 'wss://${foundry.properties.customSubDomainName}.services.ai.azure.com/voice-live/realtime?api-version=2026-04-10&model=gpt-4.1-mini'
