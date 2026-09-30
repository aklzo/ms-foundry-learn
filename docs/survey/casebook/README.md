# Foundry SI ケースブック — 要件別プレイブック・詰まりどころ索引・案件事例

> **最終更新:** 2026-09-04 / 2026-09-26(月次更新) / 2026-09-29(P-A11 注記のみ) / 2026-09-30(Port 15 ライブの実測 3 件追加) / **版:** 初版
> [features](../features/README.md) が「その機能は使えるのか」、[architecture](../architecture/README.md) が「どう組むか」、[proposal](../proposal/README.md) が「どう提案するか」に答えるのに対し、本セットは **「この要件が来たら何を決め、どこで詰まるか」** に答える。公式ドキュメント調査(survey)と実装検証([tech-selection-guide](../../tech-selection-guide.md) / labs)の**間を埋める実務層**で、公開されている第三者の記事(「ハマった」「苦労した」系)も出典として扱う唯一のセット。

## ドキュメント構成

| # | ドキュメント | 内容 | 使うタイミング |
| --- | --- | --- | --- |
| 01 | [要件シナリオ別プレイブック](./01-scenario-playbook.md) | SI で頻出する 12 の要件セットについて「ゲート判定 → 推奨構成 → 却下案と理由 → 詰まりどころ → 見積もり・契約で効く点」を 1 シナリオ 1 節で | ヒアリング直後、構成案を 1〜2 に絞るとき |
| 02 | [詰まりどころ索引](./02-pitfalls-index.md) | 機能・レイヤー別に「症状 → 原因 → 設計上の対処 → 出典」を索引化。出典は **[公式] / [実測] / [記事]** の 3 種を明記 | 設計レビュー前、提案書のリスク欄を書くとき、障害切り分け |
| 03 | [案件事例: 社内ヘルプデスク × ServiceNow](./03-case-helpdesk.md) | 外部案件で「Foundry フル活用 → 意図的撤退 → hosted agent で再挑戦」と設計判断が 3 回変わった経緯と実測。**判断が後から見てどう評価されたか**まで記録 | 「なぜ Foundry を使う / 使わないのか」を顧客に説明するとき |

## 出典の格付け(本セット固有のルール)

| 表記 | 意味 | 信頼の置き方 |
| --- | --- | --- |
| **[公式]** | Microsoft Learn / 公式ブログ / 公式サンプルリポジトリ | 一次情報。ただし**ページ間で表記が揺れる**ことがある(→ [architecture 10 章 A11](../architecture/10-migration-antipatterns.md#a11-ドキュメントのステータス表記を-1-ページだけ見て判断する)) |
| **[実測]** | 本リポジトリの labs([maf-ports](../../../labs/maf-ports/README.md) / [foundry-probes](../../../labs/foundry-probes/README.md) / [cu-video-rag](../../../labs/cu-video-rag/README.md))または外部案件([03](./03-case-helpdesk.md))で再現した事実 | 日付・バージョン付きの事実。**版が変われば結論も変わりうる** |
| **[記事]** | 第三者の公開記事(Zenn / Qiita / Tech Community / GitHub issue / Microsoft Q&A 等) | 二次情報。**執筆時点の挙動**であり、修正済みの可能性がある。採用前に日付と対象バージョンを確認し、可能なら [実測] か [公式] で裏を取る |

**[記事] を載せる基準:** (1) URL を実際に開いて内容を確認できたもの (2) 症状と原因(または回避策)が具体的に書かれているもの (3) 公式ドキュメントだけでは気づけない点を含むもの。「やってみた」だけで詰まりどころのない記事は載せない。

## 使い方(提案フローとの対応)

```
 proposal/01 ヒアリングシート ──▶ casebook/01 シナリオ照合(最も近い S-xx を 1〜2 本)
                                        │
                                        ▼
                               casebook/02 詰まりどころ抽出(S-xx が参照する P-xx を列挙)
                                        │
                                        ▼
                    提案書のリスク欄 / 設計レビューのチェック項目 / 見積もりの前提条件
                                        │
                                        ▼
                     architecture 該当章で構成を詳細化 → features で GA/プレビューを再確認
```

- シナリオは「要件の言葉」で引く。複数に跨る案件は、後戻りコストの大きいほう(閉域・マルチテナント・移行期限)を主シナリオにする
- 詰まりどころは **ID(P-xx)で提案書・設計書から参照**できるようにしてある。案件で新たに踏んだものは 02 に追記し、ID を振る
- 03 の案件事例は「判断の変遷」を含めて読む。**最初の判断が正しかったかではなく、どの根拠が後から弁別にならなかったか**が再利用できる知見

## 更新運用

**推奨頻度:** 02 は月次(公開記事・GitHub issue の追加)、01 は四半期(architecture と同サイクル)、03 は案件の節目ごと。

**[記事] のウォッチ先:**

| # | ソース | 見るもの |
| --- | --- | --- |
| 1 | Zenn(トピック `azureaifoundry` / `microsoftfoundry` / `agentframework`)、Qiita(タグ `AzureAIFoundry` / `MicrosoftFoundry`) | 日本語の「ハマった」「やってみた」記事。Ignite(11 月)・Build(5 月)直後に増える |
| 2 | [Microsoft Foundry Blog(Tech Community)](https://techcommunity.microsoft.com/category/azure-ai-foundry/blog/azure-ai-foundry-blog) | 公式の「through the corporate firewall」系トラブルシュート記事 |
| 3 | [microsoft/agent-framework issues](https://github.com/microsoft/agent-framework/issues)、[Azure/azure-sdk-for-python issues(azure-ai-projects)](https://github.com/Azure/azure-sdk-for-python/issues?q=azure-ai-projects)、[microsoft-foundry/foundry-samples issues](https://github.com/microsoft-foundry/foundry-samples/issues) | SDK・サンプルの再現性のある不具合 |
| 4 | [Microsoft Q&A(Foundry タグ)](https://learn.microsoft.com/en-us/answers/tags/133/azure) | 公式回答つきのトラブル |

**取得のコツ(2026-09-26 追記):** Tech Community の記事は既定の curl / WebFetch だとログインリダイレクトや JS レンダリングで本文が取れないことがあるが、Windows 系ブラウザの User-Agent を付けた `curl -sL` なら本文 HTML を取得できる(公開日は `datePublished`)。個人ブログの 429 はボット対策で、リンク切れではない。

**リンク切れの扱い:** [記事] は削除・移転が起きる。リンク切れを見つけたら行を消さず「(リンク切れ YYYY-MM-DD 確認)」を付記して残す(症状の記録自体に価値があるため)。

**HTML の再生成:** リポジトリルートで `python3 docs/survey/tools/md2html.py casebook`(引数なしで全セット)。

## 更新履歴

| 日付 | 内容 |
| --- | --- |
| 2026-09-30 | **02:** Port 15(delegated-access-hosted)のライブ検証から実測 3 件を末尾追加 — **P-H24**(hosted agent の会話継続は利用者ごと・agent ごとに分離され 404)、**P-O12**(プラットフォーム側 `responsesapi` スパンが会話全文を記録し、コンテナ側の設定では止まらない)、**P-C12**(Foundry アカウント配下の子リソースを並列に作ると RequestConflict)。P-I01 に hosted agent 作成での再現(`agents/write`)を付記。P-O12 は公式(トレースは接続したときだけ有効・止め方は接続解除のみ・接続文字列はコンテナにも注入)と突き合わせ、対処を architecture 09 §3.6 の 3 案(集約 / 分離 / 接続しない)に接続 |
| 2026-09-29 | features 差分更新の波及のみ。**02:** P-A11(Routines REST)に「※2026-09-29: `Foundry-Features` の値は `Routines=V2Preview`(REST 仕様では任意ヘッダー、SDK 2.5.0+ は自動付与)。V1Preview 固定のコードは外すか揃える」を注記。P-ID の追加・振り直しなし |
| 2026-09-26 | 月次更新。**02:** 外部 URL 全件の生存確認(410 の Q&A 2 件に「リンク切れ」付記、リダイレクト 5 件と転載記事 1 件を新 URL / 原文へ差し替え)、[公式] 前提の再確認で「※2026-09-26」注記(Routines GA・リージョン拡大〈P-A11〉、Toolboxes GA〈P-H12〉、idle timeout 2〜60 分〈P-H13〉、サブネット容量表と 429 `subnet_exhausted`〈P-N05〉、egress controls〈P-N07〉、incoming A2A〈P-A06〉、Foundry IQ の per-request ヘッダーと未フィルタ返却〈P-R07〉、日本 Regional +35% の価格改定〈P-M03〉、Claude の 2 系統〈P-M05〉、state store / resilience〈P-H17・H18・F06〉、公式プロトコルライブラリの stable 化〈P-H20〉、`openai>=3` 必須化〈P-F12〉、capability settings〈P-N03〉)。**訂正:** P-C06(capabilityHosts は安定版 ARM API 2025-06-01 以降にもある)、P-H06(prompt agent も版間の % 分割なし)、P-H15(旧アダプタ名の特定)。**追加:** P-H23・A12・N20・M15・G11・F13・F14。**01:** S-02 / S-03(Routines GA)/ S-04 / S-05 / S-06(セッション上限・`x-ms-user-identity`)/ S-07 / S-10(Voice Live の面別ステータス)/ S-12(egress controls)と横断節を更新。**03:** 公式側の変化の注記のみ(API version・プロトコルライブラリ・Routines・openai 3 系) |
| 2026-09-04 | 初版。01 シナリオ 12 本、02 詰まりどころ索引(公式・実測・公開記事)、03 外部案件事例(v2→v3→v4 の判断変遷と 2026-08-30 実測)を作成 |
