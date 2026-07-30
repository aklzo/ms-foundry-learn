# 04. 前提 Azure 知識マップ(Foundry 提案・設計に必要なサブセット)

[← 提案実務ガイド TOP](./README.md)

> **最終更新:** 2026-07-31
> 本リポジトリの調査ドキュメントは、いくつかの Azure 基礎知識を「知っている前提」で書かれている。**AZ-104(管理者)の全範囲は不要**で、必要なのは特定のサブセット+設計寄り(AZ-305)の観点。このマップは「どの知識が・どの設計判断で・なぜ要るか」を整理し、チームのオンボーディングとスキルギャップ確認に使う。

## 結論サマリー

- **最優先はネットワークと Entra ID。**閉域案件・ツール認証(OBO)はこの2つが分からないと設計も顧客説明もできない。
- **VM・ストレージ運用(AZ-104 の中核)はほぼ不要。**Foundry のマネージド路線ではコンピュートを直接運用しない。効くのはフロント(App Service)と self-host 比較(ACA/AKS)の場面のみ。
- 意外に効くのが**監視のコスト構造**(App Insights 取り込み課金)と **AI Search の SKU 設計**。月額を左右するのはトークン単価よりこの2つという案件も多い。

## 領域別マップ

必要度: 高 = これがないと提案・設計が成立しない / 中 = 特定の要件で必須になる / 低 = 特定構成のみ

### ネットワーク(必要度: 高)

| トピック | どの設計判断で使うか | 本リポジトリの該当箇所 |
| --- | --- | --- |
| VNet / サブネット / サブネット委任 | BYO VNet 注入(`Microsoft.App/environments` 委任、/27 以上、**作成後変更不可**)のサイジングと IP 設計 | [architecture 07](../architecture/07-usecase-regulated-edge.md) |
| Private Endpoint / Private DNS ゾーン | 閉域のインバウンド設計(Foundry は DNS ゾーン3種)。PE は自動作成されない | 同上 |
| Azure Firewall / UDR / 強制トンネリング | アウトバウンド制御。Managed VNet の FQDN ルールで Firewall が自動作成・SKU 変更不可 | 同上 |
| Application Gateway / WAF | 顧客向け公開の入口。WAF のチャット誤検知チューニングは頻出論点 | [architecture 06](../architecture/06-usecase-customer-facing.md) |
| NAT / SNAT / サービスタグ / FQDN 許可リスト | egress 許可リストの設計(AzureActiveDirectory タグ等)、SNAT 枯渇 | [architecture 07](../architecture/07-usecase-regulated-edge.md) |

学習リンク: AZ-104 のネットワークモジュール群 + https://learn.microsoft.com/ja-jp/azure/private-link/ ・ https://learn.microsoft.com/ja-jp/azure/firewall/

### ID(Entra ID)(必要度: 高)

| トピック | どの設計判断で使うか | 本リポジトリの該当箇所 |
| --- | --- | --- |
| アプリ登録 / API 権限 / 管理者同意 | Work IQ(`WorkIQAgent.Ask` 委任権限 + Global Admin 同意)等の BYO アプリ構成 | [features 04](../features/04-tools-knowledge.md) |
| **OAuth2 On-Behalf-Of(OBO)フロー** | SharePoint / Fabric 系ツールは OBO 必須(サービスプリンシパル不可)。「ユーザーの権限でデータを引く」仕組みの説明責任 | 同上 |
| マネージド ID(システム/ユーザー割当) | 接続の認証・CMK の前提条件・キーレス構成(`disableLocalAuth`) | [features 01](../features/01-platform-projects.md) |
| RBAC のスコープ設計 | Foundry 5ロール(User / Project Manager / Account Owner / Owner / Agent Consumer)+ agent スコープ。改名中は GUID 指定 | 同上 |
| agent identity とマネージド ID の区別 | prompt agent はプロジェクト共通の agent identity(サービスプリンシパル)を共有 — 監査説明で混同しない | [architecture 05](../architecture/05-usecase-agent-automation.md) |

学習リンク: https://learn.microsoft.com/ja-jp/entra/identity-platform/ (特に v2.0 フロー解説)

### 監視・ログ(必要度: 中 — コスト直結)

| トピック | どの設計判断で使うか | 本リポジトリの該当箇所 |
| --- | --- | --- |
| App Insights / Log Analytics の**取り込み課金と保持** | トレース全量記録は高額。サンプリング・保持年限・エクスポート設計 | [architecture 09](../architecture/09-operations.md)・[02 コスト手順](./02-cost-estimation.md) |
| KQL の基礎 | 監査要件(誰が何を聞いたか)の抽出、ダッシュボード自作 | 同上 |
| Azure Monitor アラート / アクショングループ | 予算アラート(**ハードリミットは存在しない**)、クォータ逼迫検知 | [02 コスト手順](./02-cost-estimation.md) |
| OpenTelemetry の概念 | Foundry トレーシングは OTel ベース。MAF / LangGraph 計装の共通言語 | [features 05](../features/05-observability-evaluation.md) |

### ガバナンス(必要度: 中)

| トピック | どの設計判断で使うか | 本リポジトリの該当箇所 |
| --- | --- | --- |
| サブスクリプション設計 / 管理グループ | 同時セッション上限・クォータは**サブスクリプション×リージョン単位** → 大規模はサブスクリプション分割 | [architecture 06](../architecture/06-usecase-customer-facing.md) |
| Azure Policy | 承認済みモデル限定(GA)・プレビューモデル禁止(プレビュー)・プレビュー UI 無効化タグ | [features 01](../features/01-platform-projects.md) |
| Landing Zone(CAF) | AI は通常ワークロードとして application landing zone へ。共有 vs 専用の5条件 | [architecture 01](../architecture/01-official-baselines.md) |
| タグ / Cost Management | チャージバック(project タグはプレビュー)・部門按分 | [02 コスト手順](./02-cost-estimation.md) |
| IaC(Bicep / Terraform) | Foundry は `Microsoft.CognitiveServices/accounts`。**capability host / ネットワーク注入は冪等更新が効かない**という Foundry 固有の癖 | [architecture 09](../architecture/09-operations.md) |

学習リンク: https://learn.microsoft.com/ja-jp/azure/cloud-adoption-framework/ ・ https://learn.microsoft.com/ja-jp/azure/well-architected/

### データサービス(必要度: 中 — RAG / standard setup で必須)

| トピック | どの設計判断で使うか | 本リポジトリの該当箇所 |
| --- | --- | --- |
| **AI Search の SKU / レプリカ / パーティション** | RAG の月額固定費の支配項。ベクトルクォータは**サービス作成日で異なる**。S3 HD はナレッジベース不可 | [architecture 04](../architecture/04-usecase-chat-rag.md) |
| Cosmos DB の RU/s | standard setup の BYO 要件(最低 3,000 RU/s/プロジェクト、Responses 利用で実質 5,000) | [architecture 07](../architecture/07-usecase-regulated-edge.md)・09 |
| Blob Storage(SAS / ライフサイクル) | ファイル取り込み・BYO ストレージ・監査ログエクスポート | — |

### コンピュート(必要度: 低 — 特定構成のみ)

| トピック | いつ必要になるか |
| --- | --- |
| App Service | チャット UI / API のフロントをホストする場合(ベースライン構成の一部)。コードファーストエージェントを Foundry 外でホストする選択肢 |
| Container Apps(+ dynamic sessions) | Code Interpreter の基盤理解、Custom Code Interpreter、自前サンドボックス実行 |
| AKS | 大規模 self-host(LangGraph 等を Foundry に載せない判断をした場合)のみ。**Foundry マネージド路線では不要** |
| VM | ほぼ不要(セルフホストランナー〈閉域 CI/CD 用〉くらい) |

## 資格との対応

| 資格 | 本マップとの関係 |
| --- | --- |
| AZ-104(Azure Administrator) | ネットワーク・ID・ガバナンスのモジュールは有効。**VM / ストレージ運用の章はスキップ可**。 https://learn.microsoft.com/ja-jp/credentials/certifications/azure-administrator/ |
| AZ-305(Solutions Architect) | 本リポジトリの用途(構成の設計判断)に最も近い。非機能要件 → 構成のマッピング訓練として有効。 https://learn.microsoft.com/ja-jp/credentials/certifications/azure-solutions-architect/ |
| AI-102(AI Engineer) | Foundry 固有部分は本リポジトリの方が新しい・深い。Speech / Vision / Language 系の基礎補完として。 https://learn.microsoft.com/ja-jp/credentials/certifications/azure-ai-engineer/ |

## 読む順序の推奨(オンボーディング)

1. **[features README](../features/README.md)** — 用語と 2025-11 改編の全体像(30分)
2. Entra ID の OBO フロー解説(外部)→ **[features 04(ツール)](../features/04-tools-knowledge.md)**(1時間)
3. **[architecture 03(判断ガイド)](../architecture/03-decision-guide.md)** → 担当案件のユースケース章(2時間)
4. 閉域案件の担当者のみ: Private Link / Firewall の基礎(外部)→ **[architecture 07](../architecture/07-usecase-regulated-edge.md)**(2時間)
5. 提案担当: **[01 ヒアリングシート](./01-hearing-sheet.md)** + **[02 コスト手順](./02-cost-estimation.md)**(1時間)
