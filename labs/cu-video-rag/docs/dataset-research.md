# データセット調査 — ナレーション付き画面操作研修動画のオープンデータ

2026-08-30 調査。結論: **日本語音声+日本語画面表示の要件を満たすオープンデータセットは見つからなかった**。
そのため本ラボは自作合成データセット(→ [design.md](./design.md))で検証する。

## 1. 要件

| 要件 | 理由 |
|---|---|
| ナレーション音声つき画面操作動画 | helpdesk 案件で実在した「画面操作手順のガイド・研修動画」を模す |
| 日本語音声(望ましい) | 書き起こし(CER)を日本語で測る |
| 画面内に日本語表示(望ましい) | CU の視覚理解(1 FPS・512×512 縮小)で日本語 UI 文字が拾えるかを測る |
| 書き起こしの正解データ | CER 算出に必須 |
| 再配布可能なライセンス | リポジトリに評価データとして同梱するため |

## 2. 調査した候補

| データセット | 内容 | 言語 | 正解書き起こし | ライセンス | 判定 |
|---|---|---|---|---|---|
| [PsTuts-VQA](https://github.com/adobe-research/PsTuts-VQA-Dataset) (Adobe Research) | Photoshop 操作チュートリアル動画 76 本(計 5.6 時間)+ 発話書き起こし + QA 17,768 問 | **英語** | あり(人手) | CC BY-NC 4.0 | 最有力だが英語。動画ファイル自体の取得手段が README から明確でない |
| [VideoGUI](https://proceedings.neurips.cc/paper_files/paper/2024/file/804e757b7d7043c26701c3a313032101-Paper-Datasets_and_Benchmarks_Track.pdf) (NeurIPS 2024 D&B) | GUI 操作の instructional video ベンチマーク(YouTube 由来) | 英語 | ベンチ用注釈のみ | YouTube 動画はリンク参照(再配布不可) | 英語+動画の再配布不可 |
| HowTo100M / YouCook2 系の instructional video データセット群 | 手順説明動画(調理・DIY 等)。画面操作(スクリーンキャスト)ではない | 英語中心 | ASR 自動字幕 | YouTube リンク参照 | ドメイン不一致 |

日本語については、Hugging Face / GitHub / 学術ベンチマーク(NeurIPS D&B 等)を
「日本語 スクリーンキャスト」「Japanese screencast / tutorial video dataset」等で
探索したが、**日本語ナレーション付き画面操作動画+正解書き起こしを再配布可能な形で
提供するデータセットは確認できなかった**(日本語の音声コーパスは会話・朗読系が中心で、
スクリーンキャスト系は存在せず)。

## 3. 判断: 自作合成データセット

| 観点 | オープンデータ(英語)を使う | 自作合成(日本語) |
|---|---|---|
| 日本語要件 | ✗(音声・画面とも英語) | ○ 音声・画面とも日本語 |
| 書き起こし正解 | △(PsTuts のみ人手) | ◎ 台本=正解(完全一致の基準) |
| 検索評価の正解 | ✗ 自分で注釈が必要 | ◎ ステップ境界時刻まで決定的 |
| 視覚情報の統制 | ✗ 何が画面のみ情報か不明 | ◎ **画面のみ情報を意図的に配置**し、視覚理解の寄与を分離測定できる |
| 再配布 | △〜✗ | ◎ 生成スクリプトごと同梱 |

合成データの限界(実世界の録画より画面がきれい・話者が単一・雑音なし)は
[findings.md](./findings.md) の考察で明記する。CER はこの条件での **上限性能** と読むこと。

## 4. 参照した Web ページ

- PsTuts-VQA Dataset (Adobe Research): https://github.com/adobe-research/PsTuts-VQA-Dataset
- VideoGUI (NeurIPS 2024 Datasets & Benchmarks): https://proceedings.neurips.cc/paper_files/paper/2024/file/804e757b7d7043c26701c3a313032101-Paper-Datasets_and_Benchmarks_Track.pdf
- Content Understanding 言語・リージョン対応(japaneast / 日本語 OCR / 音声ロケール): https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/language-region-support
- Content Understanding video 概要(研修動画ユースケース・1 FPS・512×512 制約): https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/video/overview
