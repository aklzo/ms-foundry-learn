# diagrams — アーキテクチャ図の生成

`../images/*.png` は本ディレクトリの Python スクリプトから生成する。描画ヘルパーは
[labs/maf-ports/tools/archdiagram.py](../../../../labs/maf-ports/tools/archdiagram.py)
(Pillow 自前合成。公式 Azure アイコンは `diagrams` pip パッケージ同梱のものを使用)を共有する。
規約(実線=データ/破線=テレメトリ/青=認証/橙=課金注意、図中テキストは英語 — DejaVu に日本語グリフが無いため)も
[maf-ports 側の README](../../../../labs/maf-ports/tools/README.md) に従う。

## 再生成

```bash
# リポジトリルートで
for f in docs/survey/architecture/diagrams/*.py; do
  uv run --with diagrams,pillow python "$f"
done
```

PNG は `docs/survey/architecture/images/` に上書き出力される。Markdown には
`![...](./images/<name>.png)` で埋め込み、HTML は `md2html.py` が `../images/` 参照へ自動書き換える。

## 一覧

| スクリプト | 図 | 埋め込み先 |
|---|---|---|
| `baseline-chat.py` | 公式-B Baseline Microsoft Foundry Chat | [01章 §1-B](../01-official-baselines.md) |
| `a2-knowledge-search.py` | A2 全社ナレッジ検索(AI Search 自前索引) | [04章 A2](../04-usecase-chat-rag.md) |
| `b2-hitl-automation.py` | B2 承認付き業務自動化(HITL) | [05章 B2](../05-usecase-agent-automation.md) |
| `d1-closed-network.py` | D1 規制業種・閉域(BYO VNet) | [07章 §2](../07-usecase-regulated-edge.md) |

## 新しい図を足すとき

1. 構成が近い既存スクリプトをコピーし、章の本文(ASCII 図・表)と乖離しないように描く
2. 生成 → PNG を目視確認(ラベル・エッジの重なり)→ 対象章に `![...](./images/<name>.png)` を挿入
3. `python3 docs/survey/tools/md2html.py` で HTML を再生成
