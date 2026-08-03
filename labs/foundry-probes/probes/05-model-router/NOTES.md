# Model router — 挙動発見メモ(2026-08-04 実測)

環境: model-router v2025-11-18(GA)/ japaneast / GlobalStandard cap 10

## 発見(挙動)

- **japaneast にデプロイ成功。** survey 02 のリージョン表(Australia East / East US 2 / South India / Sweden Central / West US 3)は古い。カタログ(`az cognitiveservices model list -l japaneast`)にも v2025-11-18 が載っている。→ survey 更新候補。
- **既定で非 OpenAI モデルにルーティングされる。** 5 プロンプト中 4 つが `grok-4-1-fast-reasoning`(xAI)、挨拶のみ `gpt-5-mini-2025-08-07`。survey では「非 OpenAI ルーティングはプレビュー」だが、**既定デプロイ(ルーティング先の絞り込みなし)でいきなり Grok に流れる**。
- ルーティング先はアカウントのデプロイとは無関係(このアカウントに grok / gpt-5-mini のデプロイは無い)。ルーター内部のモデルプールが使われる。
- `response.model` に実ルーティング先が返るので、後から集計・監査可能。usage もルーティング先モデルのトークン単位(reasoning_tokens も見える)。課金はルーティング先モデルの単価。
- `temperature` はルーティング先が reasoning 系(grok-4-1-fast-reasoning)でもエラーにならなかった(gpt-5.4-mini 直だと temperature 不可 — maf-ports 服の罠 — なので、ルーター経由はパラメータ互換の吸収も担っている可能性。断定は保留)。

## つまりどころ

- **データガバナンス上の要注意動作**: モデル選定を「OpenAI 系のみ」と合意している案件で model-router を無設定デプロイすると、ユーザーデータが xAI(Grok)へ流れる。ルーティング対象モデルの絞り込み(デプロイ時の model subset 設定)を必須手順にすること。
- ルーティング先は日々変わり得る(ルーターのバージョンでモデルプールが変わる)。回帰テストの再現性が要る検証では router を使わない。
- 旧版 2025-05-19 / 2025-08-07 は 2026-08-30 リタイア(survey)。既存案件で旧版を掴んでいたら移行が要る。

## SI 判断メモ

- 「コスト最適化に router」という提案は、(1) ルーティング先の許可リスト設定、(2) response.model の監査ログ化、をセットにしないと規制業種では通らない。逆にこの 2 点を付ければ「難問だけ高いモデル」の説得力ある構成になる。
