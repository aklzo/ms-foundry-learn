# 05. 公開事例集 — 提案書で引用できる Microsoft 公式事例

[← 提案実務ガイド TOP](./README.md)

> **最終更新:** 2026-08-02(初版)/ **更新頻度:** 四半期(下記「探し方」の巡回先を確認)
> **収録基準:** **Microsoft 公式(customers.microsoft.com / news.microsoft.com / 公式ブログ)が公開している事例のみ。**ベンダーや媒体の二次記事は含めない。効果数値は出典の表現のまま引用する(「約」「目標」を落とさない)。

## 使い方と注意(先に読む)

- 引用は「**社名+用途+効果数値+出典 URL**」の 1 行形式で提案書の類似事例欄に載せる。
- **事例記事の技術スタック表記は広報の粒度で粗い**(多くは「Azure OpenAI Service」としか書かれない)。事例は「同業種・同類型で公開実績がある」ことの証明に使い、**アーキテクチャ選定の根拠には使わない**(その役割は [architecture 01 章の公式リファレンス](../architecture/01-official-baselines.md))。
- ブランド変遷(Azure OpenAI Service → Azure AI Foundry → Microsoft Foundry)のため、**2024 年以前の事例はほぼ「Azure OpenAI Service」名義。**Foundry / Agent Service 名指しの事例は 2025 年以降に増えている。「Foundry の事例が少なく見える」のは主に名義の問題で、エージェント型の公式事例は日本企業を含めて存在する。
- 他社ロゴ・社名の提案書掲載は、公開事例の引用であっても自社の広報・法務ルールに従うこと。

## 日本企業 — エージェント型の事例

**Foundry / Agent Service 名指し:**

| 企業 | 業界 | 内容 | 技術(記事表記) | 効果(記事表記) | 出典 |
|---|---|---|---|---|---|
| **富士通** | IT サービス | 営業提案の作成・ナレッジ検索を自動化する営業支援エージェント | **Azure AI Foundry / Azure AI Agent Service** | **営業チームの生産性 67% 向上** | [Customer Story](https://www.microsoft.com/en/customers/story/21885-fujitsu-azure-ai-foundry) / [ja-jp 記事](https://news.microsoft.com/ja-jp/2025/05/07/250507-how-agentic-ai-is-driving-ai-first-business-transformation-for-customers-to-achieve-more/) |
| **NTT データ** | IT サービス | 従業員がリアルタイムデータを取得・操作する会話型 AI 基盤 | **Microsoft Fabric + Foundry Agent Service + Foundry** | 新ソリューションの **market 投入期間 50% 短縮**、マルチエージェント展開の基盤化 | [FY26 公式ブログ](https://blogs.microsoft.com/blog/2026/07/28/looking-back-on-microsofts-fy26-from-ai-experimentation-to-frontier-transformation/) |
| **Sky 株式会社** | ソフトウェア | Fabric + Foundry でアンケート分析・要約を自動化、AI エージェントによる「デジタルワーカー」を推進 | **Microsoft Fabric + Microsoft Foundry** | データ基盤確立(定量値は記事参照) | [Customer Story(日本語)](https://www.microsoft.com/ja-jp/customers/story/26026-sky-microsoft-fabric) |

**エージェント型だが名義は Azure OpenAI Service(2024 年の公式まとめより):**

| 企業 | 業界 | 内容 | 効果(記事表記) |
|---|---|---|---|
| **大和証券** | 金融 | 複数 AI エージェントが照会対応・市況情報を処理する「AI オペレーター」 | 24 時間対応、オペレーター負荷軽減 |
| **トヨタ自動車(パワートレーン)** | 製造 | 9 つの専門エンジニアリング領域を持つ生成 AI エージェント群「O-Beya」 | エンジニアを 24/7 支援、技術伝承 |
| **ソフトバンク** | 通信 | コールセンターの LLM 自律思考型システム(問い合わせ判断→最適回答) | 待ち時間短縮・対応の均質化 |
| **ベルシステム24** | BPO | AI と人のオペレーターを組み合わせた Hybrid Operation Loop(RAG) | 応答正答率 95%+ を目標、ナレッジ自動生成 |
| **JR 西日本** | 運輸 | 駅係員向け鉄道業務特化アシスタント | 顧客待ち時間短縮、係員教育 |

出典(上表 5 件): [AI エージェントで実現する業務効率化とイノベーション: 日本の最新事例(News Center Japan, 2024-12-18)](https://news.microsoft.com/ja-jp/2024/12/18/241218-operational-efficiency-and-innovation-enabled-by-ai-agents-latest-case-studies-from-japan/)

## 日本企業 — 生成 AI 活用(RAG・チャット・M365 Copilot)

規制業種・製造など「同業種の実績」として引く際に有効なもの。出典は行内リンクまたは上記 News Center 記事。

| 企業 | 業界 | 内容 | 効果(記事表記) |
|---|---|---|---|
| **三菱UFJ FG** | 金融 | 行内 ChatGPT(Azure OpenAI) | **110 業務ユースケース** |
| **セブン銀行** | 金融 | ATM 案内・コンタクトセンター AI | 回答精度「**約 9 割**」 |
| **弁護士ドットコム** | リーガル | 24 時間無料 AI 法律相談(過去 125 万件超の相談データ基盤) | マルチ領域対応 |
| **JAL** | 航空 | 客室乗務員の機内報告アプリ「JAL-AI」(**Phi-4 SLM** + Azure OpenAI) | **報告時間を最大 2/3 削減**、36,500 人に生成 AI 展開([出典](https://www.microsoft.com/en-us/microsoft-cloud/blog/2025/05/08/transforming-japan-with-ai-5-companies-from-the-front-lines-of-innovation/)) |
| **日清食品 HD** | 消費財 | 社内会話 AI「NISSIN AI-Chat」(Azure OpenAI + Power Platform) | IT 部門負荷 **24% 削減** |
| **三菱商事** | 商社 | 投資判断支援の社内チャット「SHINE」 | 意思決定の高速化 |
| **スクウェア・エニックス** | ゲーム | ゲームエンジンドキュメント QA ボット(Slack 統合) | 非プログラマー活用、Python コード自動生成 |
| **ナガセ(東進)** | 教育 | 200 億件超の解答データを使う個別学習レコメンド | 大学合格率「70% 以上」 |
| **住友商事** | 商社 | M365 Copilot 全社展開(8,800 ライセンス) | **年間 12 億円のコスト削減**([出典](https://www.microsoft.com/en-us/microsoft-cloud/blog/2025/05/08/transforming-japan-with-ai-5-companies-from-the-front-lines-of-innovation/)) |
| **デンソー** | 製造 | M365 Copilot 全社活用 | **月 12 時間**の作業削減 |

## グローバル — エージェント型で数値が引用しやすいもの

| 企業 | 内容 | 技術(記事表記) | 効果(記事表記) | 出典 |
|---|---|---|---|---|
| **Accenture** | 責任ある AI 統制つきでユースケース量産 | Azure AI Foundry | **4 か月で 17 ユースケース**、構築時間最大 50% 短縮見込み | [Customer Story](https://www.microsoft.com/en/customers/story/23953-accenture-azure-ai-foundry) |
| **Air India** | 顧客サービスのエージェント(仮想アシスタント) | Azure OpenAI / Foundry Models / Agent Service | **1 日 4 万件**の問い合わせ処理、数百万ドル削減 | [Azure Blog](https://azure.microsoft.com/en-us/blog/ai-agents-at-work-the-new-frontier-in-business-automation/) |
| **Atomicwork** | 社内 IT/サービスデリバリのエージェント「Atom」 | Azure AI Foundry | **6 か月で問い合わせの 65% を自動化**、応答遅延 75% 減 | [ja-jp 記事](https://news.microsoft.com/ja-jp/2025/05/07/250507-how-agentic-ai-is-driving-ai-first-business-transformation-for-customers-to-achieve-more/) |

**Copilot Studio 側の事例**(課の分業モデルで「入口は Copilot Studio」を説明する材料): Dow(輸送費の隠れ損失を数分で特定・年数億ドル削減見込み)/ Eneco(月 24,000 チャット、70% をオペレーター無しで解決)/ Virgin Money(100 万+ 対話)/ T-Mobile(83,000 ユーザー)/ BDO Colombia(業務負荷 50% 減)— 出典は同上 ja-jp 記事。

## 探し方(四半期更新の巡回先)

1. [AI ケーススタディ検索ポータル(日本語)](https://www.microsoft.com/ja-jp/ai/ai-customer-stories) — 業種・製品で絞り込み
2. [Microsoft Customer Stories](https://www.microsoft.com/ja-jp/customers) — 「Azure AI Foundry」「Copilot Studio」でフィルタ
3. [News Center Japan](https://news.microsoft.com/ja-jp/) — 日本企業のまとめ記事が定期的に出る(本ページの主要出典)
4. [Microsoft Cloud Blog の集約記事(1,000+ stories)](https://www.microsoft.com/en-us/microsoft-cloud/blog/2025/07/24/ai-powered-success-with-1000-stories-of-customer-transformation-and-innovation/) と [FY 総括ブログ(毎年 7 月末)](https://blogs.microsoft.com/blog/2026/07/28/looking-back-on-microsofts-fy26-from-ai-experimentation-to-frontier-transformation/)
5. [adoption.microsoft.com — Agent transformation stories](https://adoption.microsoft.com/en-us/ai-agents/transformation-stories/) — エージェント特化の事例集

## 更新履歴

| 日付 | 内容 |
| --- | --- |
| 2026-08-02 | 初版。日本のエージェント型 8 件+生成 AI 10 件+グローバル主要事例を公式出典つきで収録 |
