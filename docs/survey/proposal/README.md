# Foundry 提案実務ガイド

> **最終更新:** 2026-07-31 / 2026-09-26(全 5 本を一次情報で再確認)/ **版:** 初版
> [features(機能ステータス)](../features/README.md) が「その機能は使えるのか」、[architecture(設計ガイド)](../architecture/README.md) が「どう組むか」に答えるのに対し、本セットは **SI の提案活動そのもの**(ヒアリング → 構成決定 → 見積もり → リスク説明)を支援する実務ドキュメント群。

## ドキュメント構成

| # | ドキュメント | 用途 | 使うタイミング |
| --- | --- | --- | --- |
| 01 | [要件ヒアリングシート](./01-hearing-sheet.md) | 業務側の言葉から構成候補に落とすための質問リストと分岐 | 初回〜2回目の顧客ヒアリング |
| 02 | [コスト見積もり手順](./02-cost-estimation.md) | トークン量の推計 → 単価取得 → 月額試算 → PTU 判断の手順書(単価は書かない主義) | 概算提示・提案書作成 |
| 03 | [日本規制対応メモ](./03-japan-compliance.md) | ISMAP / FISC / 個情法 / 医療等と Foundry 構成の対応整理 | 規制業種の案件開始時 |
| 04 | [前提 Azure 知識マップ](./04-azure-knowledge-map.md) | 提案・設計に必要な Azure 基礎知識のサブセットと学習リンク | チームメンバーのオンボーディング |
| 05 | [公開事例集](./05-case-studies.md) | 提案書で引用できる Microsoft 公式事例(日本エージェント型・生成 AI・グローバル) | 提案書の類似事例欄・プリセールス |

## 使い方(提案フローとの対応)

1. **ヒアリング**: [01](./01-hearing-sheet.md) の質問リストで要件を採取 → 構成候補(architecture のユースケース型)を 1〜2 案に絞る → 最も近い要件シナリオを [casebook 01](../casebook/01-scenario-playbook.md) で照合し、詰まりどころ(P-ID)を [casebook 02](../casebook/02-pitfalls-index.md) から抽出
2. **実現可否チェック**: 候補構成で使う機能を [features](../features/README.md) で GA / プレビュー確認 → プレビュー依存と廃止日程をリスク一覧化
3. **概算**: [02](./02-cost-estimation.md) の手順で月額レンジを試算
4. **リスク・規制説明**: [03](./03-japan-compliance.md) で顧客説明の論点を準備
5. **体制**: [04](./04-azure-knowledge-map.md) でチームの知識ギャップを確認

## 更新方針

- 本セットは features(月次)ほど頻繁な更新は不要。**単価・規制・ISMAP 登録状況は「案件ごとに最新を確認する」設計**にしてあり、ドキュメント側には手順と参照先のみを持たせている。
- features / architecture の大型更新(Ignite・Build 後)の際に、分岐条件・チェックリストへの波及を確認する。

## 更新履歴

| 日付 | 内容 |
| --- | --- |
| 2026-07-31 | 初版作成(4ドキュメント) |
| 2026-09-04 | casebook セット(要件シナリオ別プレイブック / 詰まりどころ索引 / 案件事例)への導線を 01 の 4-1・クイックマップ末尾・アウトプット 6 と本ページの使い方に追加 |
| 2026-08-02 | **05 公開事例集を追加。**Foundry / Agent Service 名指しの日本事例(富士通・NTT データ・Sky)とエージェント型(Azure OpenAI 名義)・生成 AI 事例・グローバル事例を公式出典つきで収録。四半期更新の巡回先を明記 |
| 2026-09-26 | **全 5 本を一次情報で再確認**。01: Routines GA(2026-09-24)反映・hosted agent 同時セッション上限を 2 段(サブスクリプション×リージョン既定 2,000 / 1,000 + サブネット IP)に訂正・トラフィック分割は prompt / hosted とも非対応に訂正・閉域ツール表(File Search の公式表記変化)・Data Zone APAC の定義・Assistants 廃止済み。02: 課金単位を追記(hosted agent vCPU / GiB 時間・Foundry IQ Serverless 2026-09-13 課金開始・Voice Live・CU 3 層・Routines)、Data Zone / Regional 価格プレミアム(2026-09-01)、flex フォールバック廃止、Model router の制約更新、モデル単価 URL 差し替え。03: 国内処理 = geography 型(Japan East / West)、令和 8 年改正個情法・AI 法関連(AI 事業者ガイドライン 第 1.2 版)、DS-920、ISMAP の learn 掲載ページ、Work IQ の境界外処理、トレース VNet の現行表記。04: AI-102 退役 → AI-103、capability settings 移行中の注記。05: 日本の Foundry 事例 3 件追加・巡回先 URL 更新 |
