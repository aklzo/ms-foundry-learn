# ms-foundry-learn

Microsoft Foundry(旧 Azure AI Foundry)のキャッチアップと、SI 案件における **AI エージェント関連の技術選定・アーキテクチャ選定基準の構築**を目的としたリポジトリ。

「Foundry ポータルで足りるのか / Microsoft Agent Framework (MAF) などのコード実装が必要か / LangGraph 等の他フレームワークを選ぶべきか / そもそも Foundry に乗せるべきか」を根拠を持って判断できる状態をゴールとする。

## 構成

| パス | 内容 |
| --- | --- |
| [docs/learning-plan.md](docs/learning-plan.md) | キャッチアップ計画書(技術選定判断力の獲得を主目的に構成) |
| [docs/survey/](docs/survey/README.md) | 調査ドキュメント群(下記) |
| [docs/survey/features/](docs/survey/features/README.md) | **機能一覧・ステータス調査** — GA / プレビューをサーフェス別(ポータル / CLI / SDK)に整理。出典 URL 付き。月次更新 |
| [docs/survey/architecture/](docs/survey/architecture/README.md) | **アーキテクチャ設計ガイド** — 公式リファレンス、レイヤー別の「Foundry 機能 vs 自前実装」、ユースケース別構成、運用・移行。四半期更新 |
| [docs/survey/proposal/](docs/survey/proposal/README.md) | **提案実務ガイド** — 要件ヒアリングシート、コスト見積もり手順、日本規制対応メモ、前提 Azure 知識マップ |
| [docs/slides/](docs/slides/README.md) | **SI チーム向け共有スライド** — survey / labs の要点を 42 枚に再構成した勉強会資料(Marp。HTML / PDF 同梱) |
| [docs/tech-selection-guide.md](docs/tech-selection-guide.md) | **技術選定ガイド(実装検証ベース)** — labs の実装で実証したナレッジのみを集約(調査由来の survey とは出典分離) |
| [labs/agentic-search-maf/](labs/agentic-search-maf/README.md) | 検証ラボ: 自己評価型リサーチエージェントを MAF で実装した学習用プロジェクト |
| [labs/maf-ports/](labs/maf-ports/README.md) | 検証ラボ: awesome-llm-apps の7パターンを MAF+Foundry へ移植(Wave 1 完了。Azure リソースは検証後削除済み) |
| [labs/foundry-probes/](labs/foundry-probes/README.md) | 検証ラボ: maf-ports に乗らなかった Foundry 機能 9 本の挙動確認 probe(実測済み。リソース削除済み) |
| [labs/cu-video-rag/](labs/cu-video-rag/README.md) | 検証ラボ: Content Understanding video × AI Search × RAG の精度検証(104 本・111 問+ragas。CER 0.60% / カスタムフィールドで hit@3 0.955。PDF レポート同梱。リソース削除済み) |

## 調査ドキュメントの読み方・更新

- **Markdown が正**(生成 AI 用)。人間用 HTML は各ディレクトリの `html/` 配下に自動生成される。HTML は直接編集しない。

```bash
# HTML の再生成(features と architecture の両方)
python3 docs/survey/tools/md2html.py
```

- 更新手順・ウォッチすべき一次情報(What's new / Feature readiness at GA / model retirement schedule)は [docs/survey/features/README.md](docs/survey/features/README.md) の「更新運用ガイド」を参照。

## メモ

- 2025 年 11 月(Ignite)に Azure AI Foundry から **Microsoft Foundry** へ改称。公式ドキュメントは `/azure/foundry/`(新)と `/azure/foundry-classic/`(ハブベース)に分割されている。
- ステータスは推測で書かず、公式ページで確認できないものは「要確認」+確認 URL を記録する方針。
