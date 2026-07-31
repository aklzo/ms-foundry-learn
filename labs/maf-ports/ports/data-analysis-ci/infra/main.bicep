// data-analysis-ci ポートのエージェント固有インフラ。
//
// 固有の ARM リソースは **なし**。理由:
//   - Code Interpreter は Foundry / OpenAI v1 API の**サーバー側機能**であり、
//     ツール定義({"type": "code_interpreter", "container": {"type": "auto",
//     "file_ids": [...]}})をリクエストに載せるだけで、サンドボックスコンテナは
//     サービス側でプロビジョニングされる。Bicep で作る対象が存在しない。
//   - 元アプリの実行基盤(ローカルプロセス内の DuckDB / pandas)も、移植先の
//     実行基盤(サーバー側コンテナ)も、どちらも IaC の管理対象外 — 移植で
//     インフラ差分はゼロのまま「コード実行の所在」だけが変わる(README 参照)。
//   - ただし**コストはリソースではなくセッションに付く**: Code Interpreter は
//     セッション単位の追加課金(アクティブ 1 時間/アイドル 30 分。
//     docs/survey/features/04-tools-knowledge.md)。使わなければ課金されない
//     ステートレス構成だが、ライブスモークの実行はコンテナ課金を伴う。
//
// PORTING.md §5 の規約に従い、共有基盤への existing 参照と
// ポートが必要とする出力だけを定義する。
//
//   az deployment group create -g rg-maf-ports -f main.bicep -p baseName=mafportsw2

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
