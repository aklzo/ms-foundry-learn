# Microsoft Foundry のモデルデプロイ(ラボ用要約)

> corrective-rag ポートのサンプルコーパス。Microsoft Learn の Foundry
> ドキュメントを学習用に要約したもの(2026-07 作成、ラボ内利用)。

## デプロイの種類

Foundry リソース(kind: AIServices)にはモデルを「デプロイ」として追加する。
主なデプロイ種別:

- **Global Standard**: 従量課金(トークン単位)。トラフィックはグローバルに
  ルーティングされ、容量は 1,000 TPM 単位の「capacity」で指定する。
  ラボ・小規模用途の既定の選択肢。
- **Standard(リージョナル)**: データ処理を特定リージョンに固定したい
  場合の従量課金。
- **Provisioned(PTU)**: スループットを予約する固定課金。大規模本番向け。
- **Global Batch**: 非同期バッチ処理向けの低単価デプロイ。

Bicep では `Microsoft.CognitiveServices/accounts/deployments` リソースで
モデル名・バージョン・SKU(GlobalStandard など)・capacity を指定する。
同一アカウントへの複数デプロイは逐次作成が必要(並列デプロイは競合する)。

## 埋め込みモデル

text-embedding-3-small / text-embedding-3-large も chat モデルと同様に
デプロイとして追加する。埋め込みは入力トークン数に対する従量課金で、
chat モデルよりはるかに安価。text-embedding-3-small は 1536 次元で、
RAG のコスト効率の良い既定択とされる。

## モデルのリタイアと版管理

モデルには リタイア(提供終了)日があり、`versionUpgradeOption` で
新版への自動アップグレード方針を指定できる(例: OnceCurrentVersionExpired)。
インフラをコード化する際は、モデル名・バージョンをパラメータ化して
リタイアに追従できるようにするのが定石。

## エンドポイント

Foundry リソースは OpenAI v1 互換エンドポイント
(`https://<resource>.openai.azure.com/openai/v1`)を公開し、OpenAI SDK や
agent-framework-openai の OpenAIChatClient から base_url 指定でそのまま
呼べる。プロジェクト単位のエンドポイント(`.services.ai.azure.com/api/
projects/<name>`)は Agent Service・評価などプロジェクト API 用。
