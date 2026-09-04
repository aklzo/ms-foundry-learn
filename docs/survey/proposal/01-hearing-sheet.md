# 01. 要件ヒアリングシート(質問 → 構成への分岐)

[← 提案実務ガイド TOP](./README.md)

> **最終更新:** 2026-07-31 / 2026-09-04(casebook への導線・閉域 Lv 定義を追加)
> 初回〜2回目のヒアリング(60〜90分)を想定。各質問に「なぜ聞くか」と「回答が構成に与える影響」を付けてある。**回答をこのシートに沿って埋めると、[architecture のユースケース型](../architecture/README.md)のどれかに落ちる**ように設計している。

## 使い方

- Phase 0〜7 を順に聞く。全部で 30 問前後だが、Phase 1 の回答で無関係な Phase は飛ばせる。
- **太字の質問は「聞き漏らすと提案後に手戻りが発生する」地雷質問**。時間がなければ太字だけでも埋める。
- 末尾の「回答 → 構成クイックマップ」で構成候補とリスク一覧に変換する。

## Phase 0: 前提確認(5分)

| # | 質問 | なぜ聞くか | 回答 → 構成への影響 |
| --- | --- | --- | --- |
| 0-1 | **既存の Azure 利用はあるか。あるならサブスクリプション/Landing Zone の管理体制は?** | Foundry リソースを既存ガバナンス(Policy / RBAC / ネットワーク)に載せるか、新規に作るかが変わる | 既存 LZ あり → CAF 準拠で application landing zone へ配置([architecture 01](../architecture/01-official-baselines.md))。なし → 基盤構築から見積もりに含める |
| 0-2 | **Microsoft 365 / M365 Copilot の利用状況は?**(ライセンス種別まで) | SharePoint ツール・Work IQ は Copilot ライセンス or 従量課金が必要。Teams/M365 公開の可否も決まる | Copilot あり → SharePoint/Work IQ 経路が最短。なし → Retrieval API 従量課金の費用を見込むか、AI Search 経由の RAG に倒す |
| 0-3 | 既存の AI 利用(Azure OpenAI 直、他社 LLM、Copilot Studio 等)はあるか | 移行・共存の設計が要る。AOAI リソースは Foundry リソースへ非破壊アップグレード可 | AOAI あり → アップグレードパス([features 01](../features/01-platform-projects.md))。Copilot Studio あり → 接続はプレビュー |

## Phase 1: 業務・目的(10分)

| # | 質問 | なぜ聞くか | 回答 → 構成への影響 |
| --- | --- | --- | --- |
| 1-1 | **解決したい業務課題は何か。「誰が・何を・どれくらいの頻度で」やる業務か** | ユースケース型の判定が全ての起点 | 下の型判定表へ |
| 1-2 | 人間が最終確認するか、AI の出力がそのまま業務に流れるか(HITL の有無) | ガードレール・Task adherence・評価の要件レベルが変わる | 自動実行 → エージェント向けガードレール(プレビュー)依存のリスク説明が必須 |
| 1-3 | 失敗時の業務影響は?(誤答が金銭・法的リスクになるか) | 評価・観測性・段階リリースへの投資水準を決める | 高リスク → 評価 CI/CD ゲート + 継続的評価 + カナリア(prompt agent の FixedRatio 分割) |
| 1-4 | 成功指標は何か(工数削減率、応答時間、解決率など) | PoC の合否基準と評価器の選定に直結 | 指標 → [評価器マッピング](../features/05-observability-evaluation.md) |

**ユースケース型判定**(1-1 の回答から):

| 回答の特徴 | 型 | 参照章 |
| --- | --- | --- |
| 社内文書を検索して答えてほしい | 社内 RAG / チャット | [architecture 04](../architecture/04-usecase-chat-rag.md) |
| 定型業務を自動でやってほしい(申請処理、レポート作成等) | 業務自動化エージェント | [architecture 05](../architecture/05-usecase-agent-automation.md) |
| 顧客・会員向けに公開したい | 顧客接点(外部公開) | [architecture 06](../architecture/06-usecase-customer-facing.md) |
| 規制業種 / 閉域必須 / オンプレ・エッジ | 規制・エッジ | [architecture 07](../architecture/07-usecase-regulated-edge.md) |
| 音声・文書処理・画像生成・FT が主目的 | 特化ユースケース | [architecture 08](../architecture/08-usecase-specialized.md) |

## Phase 2: データ(15分)

| # | 質問 | なぜ聞くか | 回答 → 構成への影響 |
| --- | --- | --- | --- |
| 2-1 | **根拠にしたいデータはどこにあるか**(SharePoint / ファイルサーバー / DB / Fabric / SaaS / 紙) | RAG の取り込み経路とツール選定が決まる | SharePoint → SharePoint ツール(プレビュー・Copilot ライセンス要件)or AI Search インデクサ。DB/Fabric → Fabric data agent(プレビュー)or NL2SQL 自前。紙 → Content Understanding / DI の前処理をスコープに追加 |
| 2-2 | **データ量と更新頻度は?**(GB・件数、日次/週次/リアルタイム) | File Search(手軽・制御弱)か AI Search(制御強)か Foundry IQ かの分岐。インデックス更新設計の工数 | 小規模・静的 → File Search。大規模・要チューニング → AI Search。マルチソース・複数エージェント共有 → Foundry IQ(一部 GA、ポータルはプレビュー) |
| 2-3 | **データの機密区分は?(社外秘 / 個人情報 / 要配慮個人情報の有無)** | 閉域要否・ガードレール PII(プレビュー)・Purview 連携・[03 規制メモ](./03-japan-compliance.md)の適用範囲 | 個人情報あり → 個情法整理(委託構成)+ abuse monitoring の説明を準備 |
| 2-4 | ユーザーごとに見せてよいデータが違うか(アクセス制御の粒度) | セキュリティトリミングは RAG 設計の難所 | ユーザー別 → OBO 系ツール(SharePoint/Fabric、サービスプリンシパル不可)か、AI Search のセキュリティフィルタ自前実装。**全員同じ → 大幅に簡単になる**ので必ず確認 |
| 2-5 | データを国外に出せるか(処理・保存それぞれ) | デプロイタイプと機能制約が決まる | 国内限定 → **Regional Standard (Japan East) のみ**(Data Zone APAC は豪日韓星印で処理されうる)。安全性評価・Red Teaming・Task adherence は国外処理あり → 除外 or 合意 |

## Phase 3: ユーザー・規模・SLA(10分)

| # | 質問 | なぜ聞くか | 回答 → 構成への影響 |
| --- | --- | --- | --- |
| 3-1 | **利用者は誰で何人か。ピーク同時利用は?** | クォータ・PTU 判断・hosted agent のセッション上限に直結 | hosted agent は同時セッション既定最大約50(/26 サブネット、申請で拡大可)。大規模 → prompt agent 中心 or サブスクリプション分割 |
| 3-2 | 応答時間の要求は?(対話的 / 数秒待てる / バッチで良い) | モデル選定・デプロイタイプ・キャッシュ設計 | バッチ可 → Batch(50%引き・24h ターゲット・SLA なし)。対話 + 安定 → PTU 検討 |
| 3-3 | **可用性・SLA の要求水準は?** | プレビュー機能は SLA なし。マルチリージョン DR は「再構築」戦略が基本 | 高 SLA → プレビュー機能を構成から排除([features の GA 一覧](../features/README.md))+ spillover / model router でフェイルオーバー |
| 3-4 | 利用の波は?(営業時間集中 / 平準 / 月次ピーク) | PTU の損益分岐と spillover 構成 | ピーク型 → PTU + Standard spillover のハイブリッド([02 コスト手順](./02-cost-estimation.md)) |

## Phase 4: セキュリティ・規制(15分)

| # | 質問 | なぜ聞くか | 回答 → 構成への影響 |
| --- | --- | --- | --- |
| 4-1 | **閉域(インターネット非経由)が必須か。それは要件か希望か** | BYO VNet 注入は**作成後の変更不可**。最初に決めないと作り直しになる | 必須 → [architecture 07](../architecture/07-usecase-regulated-edge.md) の「使えない機能一覧」から設計を始める(File Search / Browser Automation / Computer Use / Image Generation / Logic Apps 等が非対応)。**「閉鎖」の Lv 定義(Lv3 = インバウンド遮断のみ / Lv4 = egress 統制・外部 SaaS・PyPI 禁止)も同時に確定**する — CI/CD・搬入・監視の設計と見積もりが別物になる([casebook S-12](../casebook/01-scenario-playbook.md#s-12-顧客閉域環境への納品-ci-cd・構築・搬入・プロンプト運用)) |
| 4-2 | 業種の規制・ガイドラインは?(FISC / 3省2 / ISMAP / 社内基準) | [03 規制メモ](./03-japan-compliance.md)の該当節を適用 | 政府 → ISMAP 登録状況の確認が先決。金融 → FISC 対応整理 + 閉域 |
| 4-3 | **Web 検索・外部サービス呼び出しを許容するか** | Web search / Bing 系は **DPA 対象外・地理境界外送信・別課金** | 不許容 → Web グラウンディング機能を全て外す(サブスクリプション単位で無効化も可) |
| 4-4 | 認証は?(Entra ID / 外部 IdP / 匿名) | Agents は Entra ID 必須(API キー不可)。顧客向けは別途 IdP 統合 | 外部 IdP → フロント側で変換。B2C 相当の設計を工数に |
| 4-5 | 監査要件は?(誰が何を聞いたかの記録・保持年限) | トレース(ポータル90日)+ App Insights 保持設計 + Purview | 長期保持 → App Insights/Log Analytics のエクスポート設計と課金を見積もりへ |
| 4-6 | CMK(顧客管理キー)要件はあるか | CMK は一部リージョンのみ・CMK→MMK 不可逆 | 要件あり → リージョン可否を先に確認 |

## Phase 5: 既存資産・統合先(10分)

| # | 質問 | なぜ聞くか | 回答 → 構成への影響 |
| --- | --- | --- | --- |
| 5-1 | 出力先はどこか(Teams / 既存 Web / 新規 UI / API / M365 Copilot) | チャネル構成が決まる | Teams/M365 → 公開フロー GA(Bot Service 必要)。既存 Web → フロント実装 + WAF([architecture 06](../architecture/06-usecase-customer-facing.md)) |
| 5-2 | 呼び出したい既存システム・API はあるか(認証方式も) | ツール選定: OpenAPI ツール(GA)/ Functions(GA・standard のみ)/ MCP(GA)/ Logic Apps コネクタ(プレビュー) | OAuth2 必須の SaaS → Logic Apps コネクタは OAuth2 非対応(プレビュー)に注意 |
| 5-3 | RPA・既存自動化(Power Automate 等)との棲み分けは? | エージェント化する範囲の合意 | 画面操作が必要 → Browser Automation / Computer Use は**プレビュー+リスク警告あり**。本番は避けるか限定 |

## Phase 6: 運用体制・スキル(10分)

| # | 質問 | なぜ聞くか | 回答 → 構成への影響 |
| --- | --- | --- | --- |
| 6-1 | **引き渡し後、誰が運用するか(顧客内製 / SI 運用委託 / ハイブリッド)** | 構成の複雑度上限が決まる | 顧客内製・非開発者 → ポータル中心(prompt agents)。開発チームあり → MAF / hosted agents も選択肢 |
| 6-2 | 顧客側の開発スキルは?(Python/.NET、Azure 経験) | portal vs MAF vs LangGraph の分岐([learning-plan](../../learning-plan.md) の選定軸) | LangChain 資産あり → LangGraph を hosted agent として持ち込む案 |
| 6-3 | プロンプト・ナレッジの更新は誰がやるか | 運用設計(バージョニング・評価ゲート)の工数 | 業務部門更新 → ポータルのバージョン管理 + 評価の自動ゲートを提案 |
| 6-4 | モデル更新(リタイア強制移行)への追従体制は? | GA モデルは約18か月でリタイア。**運用契約に「モデル移行対応」を含めるか**は契約論点 | 含める → 定期評価の再実行を運用メニュー化 |

## Phase 7: 予算・スケジュール・リスク許容度(5分)

| # | 質問 | なぜ聞くか | 回答 → 構成への影響 |
| --- | --- | --- | --- |
| 7-1 | 予算レンジ(初期 / 月額ランニング) | 構成の足切り。閉域は固定費(Firewall / PE / APIM)が支配的になる | [02 コスト手順](./02-cost-estimation.md)で概算 |
| 7-2 | **プレビュー機能の利用を許容するか(SLA なし・仕様変更あり)** | Foundry は有用機能の多く(Memory / Routines / Foundry IQ ポータル / エージェント向けガードレール等)がプレビュー | 不許容 → GA のみ構成([features README の Feature readiness](../features/README.md))+ プレビュー UI 無効化(`AZML_DISABLE_PREVIEW_FEATURE` タグ)を提案に含める |
| 7-3 | PoC → 本番のスケジュール感 | 廃止日程(Assistants 2026-08-26、Workflows 2026-12-01 等)との衝突確認 | 期間内に廃止到来 → 最初から後継 API で作る |

## 回答 → 構成クイックマップ

| ヒアリング結果の組み合わせ | 構成候補 | 主なリスク・確認事項 |
| --- | --- | --- |
| 社内 RAG + データは SharePoint + 内製運用弱 | prompt agent + SharePoint ツール(or AI Search)+ ポータル運用 | SharePoint ツールはプレビュー / Copilot ライセンス or 従量課金 |
| 社内 RAG + 大規模・検索品質重視 | prompt agent + AI Search(自前インデックス)、将来 Foundry IQ | ベクトルクォータはサービス作成日依存 / セキュリティトリミング自前 |
| 業務自動化 + 多段オーケストレーション | MAF(コードファースト)+ hosted agents | ビジュアル Workflows は 2026-12-01 廃止のため使わない |
| 顧客向け公開 + 大規模 | App Gateway/WAF + APIM + prompt agents + ガードレール | WAF 誤検知チューニング / 同時セッション・クォータ設計 / BOLA 対策自前 |
| 閉域必須(金融等) | BYO VNet 注入 + standard setup(BYO 3点)+ PE | **ネットワーク構成は作成時のみ**・使えないツール多数・Firewall 等の固定費 |
| 国内データ処理必須 | Regional Standard (Japan East) + 評価は国外の扱いを合意 | Japan East のモデル提供状況・クォータを個別確認 |
| 文書処理中心 | Content Understanding(+ DI)+ Batch | CU は BYO モデル接続必須 / ページ・サイズ上限 |

**シナリオ別の判断根拠と詰まりどころ:** 上表の構成候補ごとに、ゲート判定・却下案とその理由・詰まりどころ(P-ID)・見積もりで効く点を [casebook 01 要件シナリオ別プレイブック](../casebook/01-scenario-playbook.md) に整理してある(社内 RAG = S-01、ヘルプデスク × ITSM = S-02、承認付き自動化 = S-03、閉域 = S-04、顧客向け = S-05、SaaS = S-06、既存組込み = S-07、Copilot Studio 引き継ぎ = S-08、文書・動画処理 = S-09、音声 = S-10、廃止期限駆動の移行 = S-11、顧客環境納品 = S-12)。

## ヒアリング後のアウトプット(提案までの ToDo)

1. 構成候補 1〜2 案(architecture 該当章の構成図をベースに)
2. **プレビュー依存リスト**(機能名・現ステータス・GA 見込み不明の明記)— features から抽出
3. **廃止日程との衝突チェック**(features README の期限表)
4. 概算月額レンジ([02](./02-cost-estimation.md) の手順で)
5. 規制・契約の論点リスト([03](./03-japan-compliance.md) から該当分)
6. **詰まりどころリスト**(該当シナリオが参照する [casebook 02](../casebook/02-pitfalls-index.md) の P-ID)— 提案書のリスク欄と設計レビューのチェック項目に転記する
