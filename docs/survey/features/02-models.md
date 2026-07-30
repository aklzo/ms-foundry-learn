# 02. Foundry Models(モデルカタログ・デプロイ・ファインチューニング)

[← 機能一覧 TOP](./README.md)

> **最終更新:** 2026-07-30(2026-07-29 の初版を一次情報に当てて検証・訂正。訂正内容は [TOP の更新履歴](./README.md#更新履歴)参照)

## 概要

モデルカタログ(1,900+ モデル)、モデルファミリ別の提供状況、デプロイタイプ、Model router、モデルライフサイクル、ファインチューニング、Foundry Local を扱う。カタログは「**Models sold by Azure(Azure Direct)**」(Microsoft がホスト・販売、MS サポート・SLA・Responsible AI 審査付き)と「**Models from partners and community**」(第三者提供、Azure Marketplace 課金)の2区分で整理される。

## モデルカタログ全体像

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Model catalog (Foundry Models) | 1,900+ モデル(基盤/推論/SLM/マルチモーダル/業界特化)。2区分制 | GA(カタログ自体) | 新/classic 両対応 | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/concepts/foundry-models-overview | 用語は "sold directly by Azure" から「Models sold by Azure(Azure Direct)」表記に統一されつつある |
| Models sold by Azure (Azure Direct) | MS がホスト・販売。OpenAI / xAI / DeepSeek / Meta / Mistral / Cohere / BFL / Moonshot / Microsoft 等 | GA(枠組み) | 新ポータル「Discover > Models」 | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure | 一部モデルで PTU が fungible(モデル間流用可) |
| Models from partners and community | 第三者提供。Azure Marketplace 課金。**Anthropic Claude はこちら**(Azure Direct ではない)。Hugging Face は managed compute | GA(枠組み) | 新ポータル対応。**Hugging Face / managed compute 系も新ポータルの Foundry プロジェクトで利用可**(managed compute 自体はパブリックプレビュー) | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-from-partners ・ https://learn.microsoft.com/en-us/azure/foundry/concepts/managed-compute-overview | 初版は「classic 必須」と記載していたが誤り(2026-07-30 訂正) |
| Model leaderboards / benchmarks | カタログ内で品質・安全性・コスト・性能のリーダーボード比較 | パブリックプレビュー | Foundry ポータル | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/concepts/model-benchmarks | 品質指標は bigbench_hard, GPQA, MMLU-Pro 等 |
| Instant access (instant models) | **デプロイ不要**でモデル名指定だけで推論。新モデルは既定で instant 対応 | パブリックプレビュー | 新ポータル(playground 対応) | `az rest` で列挙可 | `azure-ai-projects` 対応(C#/TS/Java/REST も) | https://learn.microsoft.com/en-us/azure/foundry/concepts/instant-models | プレビュー中は **West US 3 のみ**。fine-tuned モデル・カスタム guardrails 不可。グローバルクォータ消費 |

## Azure OpenAI モデルファミリ

| 機能名 | 説明 | ステータス | 出典 | 備考 |
|---|---|---|---|---|
| GPT-5.6 series (`gpt-5.6-sol/terra/luna`) | 最新フラッグシップ(2026-07-09)。1.05M context、reasoning / Responses / computer use | GA | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure | Tier1-4 はクォータ申請要。リタイア 2027-07-09 |
| GPT-5.5 / 5.4 / 5.3-codex / 5.2 / 5.1 / 5 | GA 世代群 | GA(`*-chat` 系はプレビュー扱い) | 同上 | `gpt-5-chat`〜`gpt-5.3-chat` は 2026-05〜06 に**リタイア済**、後継は `gpt-chat-latest` |
| `gpt-chat-latest` | 継続更新型チャットモデル(OpenAI の chat-latest 相当) | パブリックプレビュー | 同上 | Preview ライフサイクル(随時更新) |
| o-series (o1 / o3 / o3-mini / o4-mini 等) | 旧 reasoning 系 | 非推奨(大半) | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule | o1/o3→2026-10-21(後継 gpt-5.6-sol)、o3-mini→2026-10-01、o4-mini→2026-10-16 |
| GPT-4o / GPT-4.1 | 旧世代 | 非推奨 | 同上 | gpt-4o(2024-05-13)は 2026-10-01 リタイア→gpt-5.1。gpt-4o(2024-08-06 / 2024-11-20)・gpt-4.1・gpt-4.1-mini は 2027-04-14。**⚠ `gpt-4.1-nano` のみ 2026-10-14** で本体より約半年早い(ファインチューニング対象に選ぶ際は特に注意) |
| gpt-image 系 | 画像生成: `gpt-image-1`(プレビュー)、`gpt-image-1-mini` / `gpt-image-1.5` / `gpt-image-2` | GA(gpt-image-2 は 2026-04-21 GA。gpt-image-1 のみプレビュー) | 同上 | gpt-image-1 は 2026-10-23、gpt-image-1.5 は 2026-12-16 リタイア予定 |
| Sora / Sora 2(動画生成) | テキスト/画像/動画→動画。音声付き生成・Remix 対応。非同期ジョブ API | パブリックプレビュー | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/video-generation | API は `api-version=preview`(v1 API)。sora-2 (2025-10-06) は 2026-07-15 リタイア→sora-2 (2025-12-08、retire 2026-09-15) へ |
| 音声系(realtime / audio / transcribe / tts) | `gpt-realtime`(GA)、`gpt-realtime-1.5` GA、`gpt-realtime-2`/`2.1` プレビュー、`gpt-audio` GA、`gpt-4o-transcribe` 系プレビュー、`tts`/`tts-hd` プレビュー | モデル別に混在 | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure | whisper / tts / tts-hd は 2026-12-15 リタイア予定。`gpt-realtime-translate` / `-whisper` は時間課金 |

## Anthropic Claude(パートナーモデル)

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Claude models on Foundry | パートナー枠。**2ホスティング形態**: 「Hosted on Anthropic infrastructure」/「Hosted on Azure」(**Hosted on Azure は全て GA**) | モデル別(下記) | 新ポータルで Deploy(New Foundry トグル ON) | Bicep/Terraform スターターキットあり | **Anthropic SDK**(`anthropic` の `AnthropicFoundry`、JS は `@anthropic-ai/foundry-sdk`)+REST | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-claude ・ https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models | 課金は Azure Marketplace + **CCU (Claude Consumption Units)**。CSP・クレジットのみのサブスクリプションは不可 |
| 主なモデル | `claude-opus-5`, `claude-opus-4-8`, `claude-sonnet-5`, `claude-haiku-4-5`(Hosted on Azure + Anthropic 両方 GA)。`claude-opus-4-7/4-6/4-5/4-1`, `claude-sonnet-4-6/4-5`(Anthropic infra GA)。`claude-fable-5`(プレビュー)。`claude-mythos-5` / `claude-mythos-preview`(限定プレビュー〈gated research preview〉、Entra ID 認証のみ) | 上記の通り | 同上 | — | — | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models | 注意: リタイアスケジュール側では Anthropic 掲載分が「Preview」ライフサイクル扱いで、`claude-opus-4-1` は **2026-08-05 リタイア予定**(後継 opus-4-8)、haiku-4-5 / opus-4-5 / sonnet-4-5 は 2026-10-19 予定。concepts ページ(GA 表記)と食い違いがあるため利用時は両方参照 |
| デプロイタイプ/リージョン | Global Standard(全 Claude)+ **Data Zone Standard (US)**(Hosted on Azure の opus-5 / opus-4-8 / sonnet-5) | GA(デプロイ形態) | 同上 | — | — | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-from-partners | Anthropic infra 版は eastus2 / swedencentral のみ。Azure 版は US 広域 |
| API/機能 | Messages API・Token counting。streaming、prompt caching、tool use、extended/adaptive thinking、effort(`xhigh`/`max`)、PDF/画像入力、1M context | GA(モデル準拠) | — | — | Anthropic SDK | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models | Sonnet 4.5 の 1M context beta は 2026-04-30 廃止。**Foundry 側の組み込みコンテンツフィルターなし**(自前で AI Content Safety を構成 → [06-safety-guardrails](./06-safety-guardrails.md)) |

## その他モデルファミリ(Azure Direct / パートナー)

| 機能名 | 説明 | ステータス | 出典 | 備考 |
|---|---|---|---|---|
| xAI Grok | `grok-4`, `grok-4.1-fast-*`, `grok-code-fast-1` GA。`grok-4.3`, `grok-4-20-*` プレビュー | GA/プレビュー混在 | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure | grok-4 / grok-code-fast-1 は登録制。grok-3 系・grok-4-fast 系は 2026-05-01 リタイア済 |
| DeepSeek | `DeepSeek-V4-Pro` / `V4-Flash` GA(1M ctx、retire 2028-02-20)、`V3.2` / `V3.2-Speciale` GA | GA | 同上 | R1 は Legacy(2026-08-13 リタイア予定)、R1-0528 / V3-0324 / V3.1 はリタイア済(2026-07-13) |
| Meta Llama | Azure Direct: `Llama-4-Maverick-17B-128E-Instruct-FP8`, `Llama-3.3-70B-Instruct` GA。パートナー枠: `Llama-4-Scout` GA | GA | 同上 | Llama 3.1/3.2 系は 2026-06-13 リタイア済 |
| Mistral | Azure Direct: `Mistral-Large-3` GA、`mistral-document-ai-2512` GA、`mistral-medium-3-5` プレビュー、`mistral-ocr-4-0` プレビュー。パートナー枠: Codestral-2501 / Ministral-3B 等 GA | 混在 | 同上 | mistral-document-ai-2505 はリタイア済 |
| Microsoft (Phi / MAI) | Phi-4 ファミリ(mini/multimodal/reasoning 含む)は**パートナー枠で全て GA**。`MAI-Image-2.5` 系はプレビュー | 混在 | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-from-partners | MAI-Image-2/2e は 2026-08-15 リタイア予定 |
| BFL FLUX / Cohere / Moonshot / Stability | FLUX.2-pro/flex ほか GA(マルチ参照画像はプレビュー扱い)。Cohere rerank v4 / command-a GA、`command-a-plus` プレビュー。Kimi K2.5/2.6/2.7-Code プレビュー。Stability SD3.5 系は非推奨(2026-07-31 リタイア予定) | 混在 | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure ・ https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule | — |

## デプロイタイプ

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Global Standard | グローバルルーティング・従量課金。最大クォータ | GA | 対応(SKU: `GlobalStandard`) | Azure Policy / ARM 対応 | 対応 | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types | 新モデルは Global Standard から順に展開。Priority processing はプレビュー |
| Global / Data Zone / Regional Provisioned (PTU) | 予約キャパシティ。PTU は**モデル非依存(fungible)**・リージョン別クォータ | GA | 対応 | 対応(sku-name 指定) | REST/ARM | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/provisioned-throughput | 時間課金 + Azure Reservations(1か月/1年)。モデル自動アップグレード対象外(手動移行) |
| Global Batch / Data Zone Batch | 非同期一括処理、24h ターゲット、**50%割引** | GA | 対応 | — | — | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types | リアルタイム SLA なし |
| Data Zone Standard | EU / US / **APAC** データゾーン内処理 | GA | 対応 | — | — | 同上 | APAC ゾーン(豪・日・韓・星・印)の追加が比較的新しい |
| Standard (Regional) | 単一リージョン処理・従量課金 | GA | 対応 | — | — | 同上 | 旧モデルのリタイアに伴い提供順は最後 |
| Developer (`DeveloperTier`) | **fine-tuned モデル評価専用**。SLA・データ所在保証なし | GA(用途限定) | 対応 | — | — | 同上 | **24時間で自動削除** |
| Serverless API deployments(旧 MaaS) | hub-based プロジェクトでのサーバーレスエンドポイント | 非推奨予定(明示的な deprecated 表記はないが **classic 限定+「Foundry resources へのデプロイを推奨」と明記** → 実質レガシー) | classic のみ | `az ml serverless-endpoint` | `azure-ai-ml` (ServerlessEndpoint) | https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/deploy-models-serverless | 新規設計では Foundry リソース + Global Standard / Data Zone を選ぶのが現行ガイダンス |
| Managed compute | オープンソース/コミュニティモデル(Hugging Face Collection、`azure-huggingface` レジストリ)を専用 GPU にデプロイ。VM のプロビジョニング・K8s 運用・コンテナイメージ作成は不要 | **パブリックプレビュー**(「Managed compute in Foundry is currently in preview. … we don't recommend it for production workloads」) | **新ポータルの Foundry プロジェクトで利用可**(classic 必須ではない) | 対応 | 対応 | https://learn.microsoft.com/en-us/azure/foundry/concepts/managed-compute-overview | SKU `GlobalManagedCompute`、**現時点は Global スコープのみ**。課金は**アクセラレータ単位の時間課金**(A100 80GB / H100 80GB / MI300X)。クォータはアクセラレータファミリ×リージョンで **Azure VM クォータとは別枠**。ランタイムは vLLM / SGLang / TensorRT-LLM / NIM / TEI / llama.cpp / hf-serve から自動選択。**組み込み Content Safety がデータパスに入らない**(自前で Content Safety API を呼ぶ)。モデル重みは事前ステージング済みで **Hugging Face Hub への外向き通信が不要**(完全閉域でデプロイ可) |
| Spillover(PTU→Standard 溢れ処理) | PTU 枯渇時(429/400/500/503)に同一リソースの standard デプロイへ自動転送 | GA | 新ポータル対応(Traffic spillover トグル) | REST (`spilloverDeploymentName`) | ヘッダー `x-ms-spillover-deployment` で per-request 制御 | https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/spillover-traffic-management | PTU 対応の Azure OpenAI モデルは全対応。DeepSeek / Llama は非対応。Agent Service とも併用可 |

## Model router

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Model router | プロンプトを品質/コスト基準で最適モデルへ自動ルーティング。単一デプロイで複数モデル | GA(version `2025-11-18`。retire 2027-05-20)。**非 OpenAI モデル(Grok / DeepSeek / Llama / gpt-oss / Claude)のルーティングはプレビュー** | 新ポータル(Quick/Custom deploy) | Azure CLI・ARM で Policy 統制可 | 通常のチャット API 経由 | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-router ・ https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule | 旧版 2025-05-19 / 2025-08-07 はプレビューのまま 2026-08-30 リタイア予定。ルーティングモード(Balanced/Quality/Cost)、model subset、自動フェイルオーバー、エージェント対応。Claude は事前デプロイ必須。リージョン: Australia East / East US 2 / South India / Sweden Central / West US 3 |

## モデルライフサイクル・リタイアメント

| 機能名 | 説明 | ステータス | 出典 | 備考 |
|---|---|---|---|---|
| Model lifecycle & support policy | 5段階: Preview → GA → Legacy(任意)→ Deprecated → Retired。GA は起点から 18 か月でリタイア(12 か月で新規顧客不可)、Preview は 90 日目安+強制アップグレード | GA(ポリシー) | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements | 通知: GA 60 日前 / Preview 30 日前。Standard 系は自動アップグレード、**Provisioned は手動**。Models API の `lifecycleStatus` は表記が異なる(`Deprecating`=非推奨、`Deprecated`=廃止済)点に注意 |
| Model retirement schedule | 全モデルのリタイア日一覧 | 随時更新 | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule | 直近の要注意: gpt-4o 2026-10-01、o1/o3 2026-10-21、o4-mini 2026-10-16。embeddings 系は 2028-02-09 まで延長 |

## ファインチューニング

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| SFT (Supervised fine-tuning) | ラベル付きデータで教師あり FT | GA | 新ポータル(Build > Fine-tune) | REST | OpenAI SDK v1 / `azure-ai-projects` | https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/fine-tuning | 対応: gpt-4o(-mini), gpt-4.1(-mini/-nano)。OSS 系(Ministral-3B, Qwen-32B, Llama-3.3-70B, gpt-oss-20b)は**パブリックプレビュー**かつ新 Foundry UI + Foundry リソース限定・Global training のみ |
| DPO (Direct Preference Optimization) | 選好データでアライメント | GA | 同上 | 同上 | 同上 | 同上 | 対応: gpt-4o, gpt-4.1, gpt-4.1-mini/nano |
| RFT (Reinforcement fine-tuning) | グレーダー報酬で最適化 | GA | 同上 | 同上 | 同上 | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure | 対応: o4-mini (GA)、gpt-5(GA だが招待制・アカウントチーム経由) |
| Global Training | リージョン横断トレーニング(割安、データ所在保証なし) | GA相当(明示的プレビュー表記なし) | 対応 | REST (`trainingType: GlobalStandard`) | `extra_body={"trainingType": "GlobalStandard"}` | 同上 | 対応リージョン 25(Japan East 含む。Japan East は vision 非対応) |
| Developer tier(FT 用) | アイドル容量利用の最安トレーニング+評価用デプロイ | GA(用途限定) | 対応 | REST | `trainingType: developerTier` | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types | SLA なし・プリエンプションあり・デプロイは 24h で削除 |
| Fine-tuned モデルのリタイア | training と deployment の2段階リタイア | ポリシー | — | — | — | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements | 例: gpt-4o FT は deployment 2027-10-01 まで。15 日未使用デプロイは自動削除 |

## Foundry Local(オンデバイス)

| 機能名 | 説明 | ステータス | 出典 | 備考 |
|---|---|---|---|---|
| Foundry Local | オンデバイス AI 実行(ONNX Runtime、約 20MB ランタイム)。GPT-OSS / Qwen / DeepSeek / Mistral / Phi / Whisper 等の最適化カタログ。OpenAI 互換 API(Responses API 形式含む) | GA(**2026-04-09 に公式ブログで GA 宣言**: https://devblogs.microsoft.com/foundry/foundry-local-ga/ 。docs ページ https://learn.microsoft.com/en-us/azure/foundry-local/what-is-foundry-local にはラベルなし) | 同左 | Windows / macOS (Apple silicon) / Linux。SDK: C#, JavaScript, Rust, Python。Azure サブスクリプション不要。サーバー用途は非推奨(vLLM 等を案内)。企業向けに別製品「Foundry Local on Azure Local」(Arc 対応 K8s)あり |

## 補足ノート(SI 判断に効く要点)

- **⚠ Fireworks 系モデルは予告期間が 15 日しかない**: リタイアスケジュールに Important として「**Fireworks models on Standard (Per-Token) inference offerings are subject to a 15-day notice period prior to model retirement**」と明記。標準ライフサイクル(GA は 60 日前通知)と比べて極端に短く、`FW-*` 系(GLM / Kimi / Qwen / MiniMax / DeepSeek の Fireworks 版)を本番の必須経路に置くとガバナンス上のリスクになる。掲載上のリタイア日は 2027-07-01 だが、この予告条項が優先する。
- **日本語モデル**: **NTT Data の `tsuzumi-7b` は Legacy で 2026-08-31 リタイア(後継 `tsuzumi2`)**。SFT(教師ありファインチューニング)の対応モデルとしても挙げられているため、日本語特化モデルを検討する案件では後継への切替を前提にする。
- **Claude の位置づけ**: Claude は「Models sold by Azure」ではなく Marketplace 経由のパートナーモデル。ただし「Hosted on Azure」形態が登場し opus-5 / opus-4-8 / sonnet-5 / haiku-4-5 は Azure 基盤で GA + Data Zone (US) 対応まで来ており、「パートナーモデルはデータ所在が弱い」という従来の前提が変わっている。SDK は Azure OpenAI SDK ではなく **Anthropic SDK(AnthropicFoundry)+ Entra ID** という点が実装上の分岐点。
- **serverless API deployments は実質レガシー**: classic 専用記事となり「Foundry resources への standard deployment を推奨」と明記。新規設計では選ばない。
- **ドキュメント間の齟齬**: Claude 各モデルのライフサイクルは concepts ページ(GA 表記)とリタイアスケジュール(Preview 表記+リタイア日)で食い違いあり。本番採用時は retirement schedule 側の日付を確認する。
- **ページ不在**: 新ドキュメント側の `/azure/foundry/concepts/fine-tuning-overview` は 404(FT 概要は `/azure/foundry/openai/how-to/fine-tuning` と classic 側に分散)。
