# docs/survey — Microsoft Foundry 調査ドキュメント

SI の技術選定・アーキテクチャ選定基準の構築を目的とした調査ドキュメント群。

| ディレクトリ | 内容 | 人間用 HTML |
| --- | --- | --- |
| [features/](./features/README.md) | **機能一覧・ステータス調査**(GA / プレビューをサーフェス別に整理)。「その機能は使えるのか」を引く | `features/html/index.html` |
| [architecture/](./architecture/README.md) | **アーキテクチャ設計ガイド**(公式リファレンスアーキテクチャ、レイヤー別の「Foundry 機能 vs 自前実装」、ユースケース別構成、運用・移行)。「どう組むか」を決める | `architecture/html/index.html` |
| [proposal/](./proposal/README.md) | **提案実務ガイド**(要件ヒアリングシート、コスト見積もり手順、日本規制対応メモ、前提 Azure 知識マップ)。「どう提案するか」を支援する | `proposal/html/index.html` |

**更新頻度の目安:** features は月次(What's new が月次更新のため)、architecture は四半期(骨格の変化が遅いため)。proposal は随時(単価・規制は「案件ごとに最新確認」の設計のため頻繁な更新は不要)。いずれも Ignite(11 月)・Build(5 月)直後は必ず更新する。

## HTML の生成

Markdown が正(生成 AI 用)。人間用 HTML は共有ビルダーで生成する。**HTML を直接編集しないこと。**

```bash
python3 docs/survey/tools/md2html.py              # features と architecture の両方
python3 docs/survey/tools/md2html.py architecture # 指定セットのみ
```

`docs/survey/features/tools/md2html.py` は features のみをビルドする後方互換シムとして残してある。
