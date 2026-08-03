# Guardrails / コンテンツフィルター — 挙動発見メモ(2026-08-04 実測)

環境: gpt-5.4-mini / 既定 RAI ポリシー `Microsoft.DefaultV2`(`az ...deployment show` で確認)

## 発見(挙動)

- **既定で全応答に content_filter_results / prompt_filter_results が付く**(Chat Completions の Azure 拡張フィールド)。カテゴリは hate / self_harm / sexual / violence(severity: safe/low/medium/high)+ protected_material_code / protected_material_text(detected 型)。入力側 `prompt_filter_results` には **jailbreak** カテゴリも含まれる。
- **既定ポリシー名は `Microsoft.DefaultV2`**。survey どおり編集不可・text/image とも Medium 閾値。
- **Prompt Shields(jailbreak)が既定で作動**: DAN 系の脱獄プロンプトは入力段で `jailbreak: {detected: True, filtered: True}` となり **400 `content_filter` / innererror `ResponsibleAIPolicyViolation`** で弾かれる。モデルまで到達しない。
- 一方、**素朴な有害依頼(危害の手順)は入力段ではブロックされず**、モデルが応答(拒否)を返した。既定 Medium 閾値の下では「テキストの有害リクエスト」はフィルタ発火せずモデルの refusal に委ねられるケースがある = フィルタとモデル refusal は別レイヤ。

## つまりどころ

- **ブロックは 2 系統ある**: (1) Prompt Shields / コンテンツフィルターによる 400 例外、(2) モデル自身の refusal(200 で返る)。アプリは 400 だけでなく 200 の拒否文言も「安全側の結果」として扱う設計が要る。
- 400 の `code` は `content_filter`、詳細は `innererror.content_filter_result` にカテゴリ別 detected/filtered。ログ収集はこのネスト構造を掘る必要がある。
- Responses API 側は Chat Completions ほど content_filter_results が素直に露出しない(注釈は message 側)。フィルタ結果を機械処理したいなら Chat Completions が観察しやすい。
- 管理面(ポリシー作成・閾値変更・Off 申請)は **ポータル + ARM REST(raiPolicies)のみ**。CLI/SDK に専用コマンドが無い(survey 06)。probe は既定ポリシーの観察に留め、カスタムポリシーは ARM デプロイが要る。

## SI 判断メモ

- Claude / managed compute は既定フィルタ非適用(survey 06 補足2)。それらを使う案件では Content Safety を別途噛ませる設計が必須。この差は提案時の安全性説明で必ず効く。
- 規制業種向けには「jailbreak は 400 で機械的に落ちる/有害依頼はモデル refusal に依存」の 2 レイヤをそのまま図示して説明できる(本 probe ログが根拠)。
