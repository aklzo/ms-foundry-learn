# 03. 日本規制対応メモ(ISMAP / FISC / 個情法 / 医療)

[← 提案実務ガイド TOP](./README.md)

> **最終更新:** 2026-07-31 / 2026-09-26(Data Zone APAC・閉域ツール表・トレース VNet の現行表記、個情法 令和 8 年改正・AI 法関連の最新版、ISMAP の learn 掲載ページ、Work IQ の境界外処理を反映)
> **免責: 本メモは SI の技術側が論点を整理するためのもの。法解釈・規制適合の最終判断は必ず顧客の法務・コンプライアンス部門と行うこと。**「検証済み」と記した項目は 2026-07 時点の learn.microsoft.com 現行ページで確認済みの事実([features](../features/README.md) / [architecture](../architecture/README.md) の調査に基づく)。

## 0. 前提: データフローの4層整理

規制の議論はまず「どのデータがどこへ行くか」を4層に分けると噛み合う:

| 層 | 内容 | 制御手段 |
| --- | --- | --- |
| ① 推論データ(プロンプト/応答) | モデルが処理する。**保存されない(stateless)・学習に使われない**と公式明記(検証済み) | デプロイタイプで処理地域を制御 |
| ② 保存データ(会話履歴・ファイル・ベクトル) | Agent Service 等が保存 | basic(MS 管理)/ standard(BYO リソース)、CMK、リージョン |
| ③ 悪用監視データ | 検出時にサンプルがレビュー対象(同一ジオ保存)。**自動レビューが既定、必要時に人間レビュー** | Modified 申請でデータ保存・人間レビューをオプトアウト可(検証済み。`ContentLogging=false` で確認可能) |
| ④ ツールの外部送信 | Web search / Bing 系はコンプライアンス境界外へ送信・**DPA 対象外**(検証済み)。**Work IQ(プレビュー)も「Foundry のサービス境界を越え、Azure コンプライアンス境界外で処理されうる」と明記**(work-iq ページ 2026-09 更新) | 機能を使わない(サブスクリプション単位無効化可)or 顧客合意 |

## 1. ISMAP(政府情報システム)

- **learn.microsoft.com 上に Foundry と ISMAP を結びつける記述は見当たらない**(2026-07 調査時点。検証済み)。learn の ISMAP オファリングページ( https://learn.microsoft.com/en-us/compliance/regulatory/offering-ismap 、2026-06-02 更新)は対象を「Azure, Microsoft Dynamics 365, and other Microsoft online services」/ Japan East・Japan West ほか 40 リージョンと**包括的に**記すのみで、個別サービス名の列挙はない(2026-09-26 確認)。
- 政府案件では **ISMAP クラウドサービスリスト( https://www.ismap.go.jp/ )で対象サービスの登録状況を案件ごとに確認する**のが先決。Azure 全体が登録されていても、**個別サービス(Foundry / Agent Service / 各ツール)が対象範囲に含まれるかは別問題**。
- 確認手順: ① ISMAP ポータルで Microsoft の登録サービス一覧を取得 → ② 構成で使う Azure サービスを列挙([01 ヒアリング](./01-hearing-sheet.md)の構成候補から)→ ③ 差分(未登録サービス)を特定し、代替構成か所管との調整かを判断。
- 政府(府省庁)案件では、デジタル庁の **DS-920「行政の進化と革新のための生成AIの調達・利活用に係るガイドライン」**(Normative、最終改定 2026-06-12)が生成 AI 調達・利活用のルールになる。調達仕様・リスク評価の要求事項を先に確認する( https://www.digital.go.jp/resources/standard_guidelines )。
- **プレビュー機能は避ける**: Azure Government 向けページには「Preview 機能は GA と同等のコンプライアンス保証(FedRAMP 等)を持たない場合がある」と明記されている(検証済み)。日本の認証でも同じ前提で扱うのが安全。

## 2. データ所在(全規制共通の土台)

| 論点 | 事実(検証済み) | 提案での扱い |
| --- | --- | --- |
| 推論の国内処理 | **geography 型(Standard / Regional Provisioned)を Japan East / Japan West に置いた場合のみ日本国内処理**(「customer-specified Azure geography 内で処理、運用目的で geography 内のリージョン間処理あり」)。Data Zone (APAC) は「APAC 域内のいずれかの国」で処理 — 現行の対象リージョンは豪・日・韓・星・印で、**Microsoft が予告なくリージョンを追加しうる**と明記(deployment-types 2026-08-06 版 / region-availability 2026-09-03 版) | 「国内必須」なら geography 型。geography 型は新モデルの提供が最後で日付保証なし → モデル提供状況・クォータは Japan East / West で個別確認。Data Zone / Regional は Global 比の価格プレミアムあり(2026-09-01 改定、[02 コスト手順](./02-cost-estimation.md)) |
| 保存データ | 保存は指定ジオグラフィ内。standard setup なら BYO リソース(Cosmos/Storage/AI Search)を Japan East に置ける | 保存層の所在は構成で完全制御可能と説明できる |
| ファインチューニング | Global Training は**データ所在保証なし**。リージョナル学習を選ぶ | FT 案件はトレーニングタイプを明示 |
| 安全性評価・Red Teaming | 対応リージョンは国外のみ(日本非対応)。**評価のためにプロンプト・応答が国外に渡る** | 使うなら明示合意、使わないなら構成から除外 |
| Task adherence(ガードレール) | データが指定 Geo 外(US/EU)で処理される可能性を公式明記 | 同上 |
| Claude 等パートナーモデル | Hosted on Azure 版は US 系(Data Zone US)。**日本国内処理の選択肢はない**(2026-07 時点。models-from-partners 2026-09-21 版でも Claude の Data Zone は US のみ・APAC なし) | 国内要件がある案件では Azure OpenAI 系を選ぶ |

## 3. 個人情報保護法

- **プロンプトに個人データを含める構成**は、Azure OpenAI の位置づけ(処理の委託)を前提に利用目的・委託先管理の整理を顧客法務と行う。技術側が用意する材料:
  - data-privacy ページの「NOT リスト」(他の顧客に提供されない / OpenAI に提供されない / モデル改善に使われない / 許可なく基盤モデルの学習に使われない。検証済み)
  - **悪用監視のオプトアウト状況**: 既定では検出サンプルの保存+レビューがある。Modified 申請が通れば保存・人間レビューなし(`ContentLogging` 属性で客観的に示せる。検証済み)
- **要配慮個人情報**(病歴等)を扱う場合は、悪用監視オプトアウト+閉域+保存層 BYO を揃えるのが説明しやすい構成。
- ガードレールの **PII 検出/リダクションはプレビュー**(検証済み)。「PII を自動でマスクします」を確約に使わない。個人情報保護委員会の生成 AI に関する注意喚起(利用目的・本人通知まわり)も法務確認の際に参照。
- **令和 8 年改正個人情報保護法(2026-07-10 成立・07-17 公布)**: 統計作成等を行う第三者への提供の同意不要化(AI 開発等の統計処理目的)、顔特徴データ等の利用停止請求、課徴金制度の新設、子どもの個人データの規律強化など。**施行は一部を除き公布から 2 年以内の政令で定める日**で、政令・規則・ガイドラインは個人情報保護委員会が整備中(2026-09 時点)。長期案件では施行日と改正ガイドラインを法務確認の論点に入れる( https://www.ppc.go.jp/personalinfo/legal/r8kaiseihogohou/ )。
- **AI 固有の国内ルール(法的拘束力の強さが異なる)**: AI 法(人工知能関連技術の研究開発及び活用の推進に関する法律。2025-06-04 公布・09-01 全面施行)/ 同法に基づく「適正性確保に関する指針」(AI 戦略本部 2025-12-19 決定)/ **AI 事業者ガイドライン 第 1.2 版**(総務省・経産省 2026-03-31。AI エージェントの定義を本編に追加)。SI は「AI 提供者」側の整理を求められうるため、顧客の AI ガバナンス規程とあわせて確認する( https://www8.cao.go.jp/cstp/ai/ai_act/ai_act.html ・ https://www.meti.go.jp/shingikai/mono_info_service/ai_shakai_jisso/20260331_report.html )。

## 4. 金融(FISC 安全対策基準)

- Microsoft は FISC 対応のリファレンス(対応状況の整理資料)を **Service Trust Portal( https://servicetrust.microsoft.com/ )**で提供している。案件では最新版を取得し、構成要素(Foundry / AI Search / APIM 等)ごとの対応状況を顧客の FISC チェックリストへマップする。
- 技術構成の定石は [architecture 07(規制業種)](../architecture/07-usecase-regulated-edge.md) の閉域構成: BYO VNet 注入(**作成後変更不可**)+ Private Endpoint + standard setup(BYO 3点)+ CMK(一部リージョンのみ)。
- 金融で刺さりやすい注意点(検証済み):
  - **Risks & safety モニタリング(悪用状況ダッシュボード)は classic ポータル専用**で新ポータル未移植(ステータスもプレビュー)
  - 閉域では Logic Apps / Browser Automation / Computer Use / Image Generation / Fabric data agent 等が使えない(configure-private-link 2026-08-14 版のツール表)。File Search は同表で「Supported(private endpoint 経由)」に変わったが、閉域での実測では vector store 作成が失敗しており提案しない([casebook P-N13](../casebook/02-pitfalls-index.md))。Bing / Web search / SharePoint は閉域でも動くが公開エンドポイント経由
  - トレースの VNet 対応: configure-private-link 2026-08-14 版の制限表から Traces 行は消えたが、GA 一覧表は「Tracing VNet = Preview」かつ「Traces は network isolation に完全には対応していない」と記載 — 安全側は「監査ログは閉域外に出る前提で設計」
  - Customer Lockbox は**非サポート**(セキュリティベースラインに明記)

## 5. 医療(3省2ガイドライン)

- 論点は「医療情報システムの安全管理」への対応: データ所在(§2)+ アクセス制御 + 監査証跡。
- 技術側の対応部品: Entra ID 必須認証(Agents は API キー不可)/ RBAC(Foundry 5ロール)/ トレース・App Insights の監査ログ設計(保持年限は Log Analytics 側で)/ Purview 監査(従量課金有効化が前提。検証済み)。
- 診療情報を含む RAG は、悪用監視オプトアウト+閉域+国内処理(geography 型 = Standard / Regional Provisioned を Japan East / West に配置)の3点セットを基本形として提示。

## 6. 契約・知財まわり(業種横断)

| 論点 | 事実(検証済み) | 顧客説明のポイント |
| --- | --- | --- |
| DPA 対象外機能 | Web search / Grounding with Bing は DPA 対象外・地理境界外送信・別課金 | 使う場合は契約上の扱いを明示合意。不要なら無効化(サブスクリプション単位可) |
| 著作権(CCC) | Customer Copyright Commitment には条件がある: Protected material 検出等の構成が前提になり得る。**非同期フィルターのストリーミング遅延分は CCC 対象外の可能性**を公式明記 | 「規約通りのガードレール構成を維持すること」を運用要件に含める |
| Claude の安全機構 | **Foundry の組み込みコンテンツフィルターは Claude に適用されない**(Anthropic 側の安全機構+自前で Content Safety を構成) | マルチモデル構成ではモデルごとに責任分界が異なることを図で説明 |
| プレビュー機能 | SLA なし・仕様/課金変更あり・コンプライアンス保証が GA と異なる場合あり | **「プレビュー利用同意書」を取る**か、GA のみ構成+プレビュー UI 無効化(`AZML_DISABLE_PREVIEW_FEATURE`) |
| モデルリタイア | GA 後 12〜18 か月でリタイア(強制移行。温度感 18 か月・安全側 12 か月) | 保守契約に「モデル移行対応」と再見積もり条項を入れる |

## 7. 顧客からの定番質問と回答の型

| 質問 | 回答の型 |
| --- | --- |
| 「入力したデータが AI の学習に使われませんか」 | ①推論データは保存されず学習に使われない(公式 NOT リスト)。②ただし悪用監視で検出時サンプル保存があり得る → オプトアウト申請の説明。③ Web 検索系ツールは別枠(DPA 対象外)なので使う/使わないを合意 |
| 「データは国内に留まりますか」 | 4層に分けて回答: 保存=構成で国内固定可 / 推論=geography 型(Standard / Regional Provisioned、Japan East / West)なら国内 / 悪用監視=同一ジオ / ツール=機能による(Web 系は境界外) |
| 「誰が会話ログを見られますか」 | RBAC(5ロール)+ プロジェクト分離 + トレースの閲覧権限(Log Analytics Reader)で説明。Microsoft 側は悪用監視の限定レビューのみ(オプトアウト可) |
| 「AI が変なことを言ったら止められますか」 | ガードレール(モデル向け GA / エージェント向けプレビュー)+ ブロックリスト + HITL 設計。**「完全には防げない」前提で評価・監視・人間承認の多層防御**を提案するのが誠実 |

## 出典(主要)

- データプライバシー: https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy
- 悪用監視: https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/abuse-monitoring
- デプロイタイプ(処理地域): https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types
- セキュリティベースライン: https://learn.microsoft.com/en-us/security/benchmark/azure/baselines/azure-ai-foundry-security-baseline
- Service Trust Portal(FISC 等): https://servicetrust.microsoft.com/
- ISMAP ポータル: https://www.ismap.go.jp/
