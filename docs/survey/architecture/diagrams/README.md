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

## 一覧(全 18 枚)

| スクリプト | 図 | 埋め込み先 |
|---|---|---|
| `baseline-chat.py` | 公式-B Baseline Microsoft Foundry Chat | [01章 §1-B](../01-official-baselines.md) |
| `a1-prompt-rag-variants.py` | A1/A3/A4 Prompt agent + マネージドナレッジ 3 変種(統合) | [04章 A1](../04-usecase-chat-rag.md) |
| `a2-knowledge-search.py` | A2 全社ナレッジ検索(AI Search 自前索引) | [04章 A2](../04-usecase-chat-rag.md) |
| `a5-foundry-iq.py` | A5 Foundry IQ(agentic retrieval) | [04章 A5](../04-usecase-chat-rag.md) |
| `b1-agent-core-api.py` | B1 単一エージェント + 基幹 API(Toolbox / 認可) | [05章 B1](../05-usecase-agent-automation.md) |
| `b2-hitl-automation.py` | B2 承認付き業務自動化(HITL) | [05章 B2](../05-usecase-agent-automation.md) |
| `b3-durable.py` | B3 長時間・確実な再開(Durable Extension + DTS) | [05章 B3](../05-usecase-agent-automation.md) |
| `b4-multi-agent.py` | B4 マルチエージェント(専門分化 + A2A) | [05章 B4](../05-usecase-agent-automation.md) |
| `b5-flow-engine.py` | B5 業務フローエンジン主導(Logic Apps / Copilot Studio) | [05章 B5](../05-usecase-agent-automation.md) |
| `c2-multitenant-saas.py` | C2 マルチテナント SaaS | [06章 C2](../06-usecase-customer-facing.md) |
| `d1-closed-network.py` | D1 規制業種・閉域(BYO VNet) | [07章 §2](../07-usecase-regulated-edge.md) |
| `d3-edge-onprem.py` | D3 エッジ・オンプレ 3 形態 | [07章 §9](../07-usecase-regulated-edge.md) |
| `e1-voice.py` | E1 音声エージェント(Voice Live + ACS) | [08章 E1](../08-usecase-specialized.md) |
| `e2-idp.py` | E2 文書処理・IDP パイプライン | [08章 E2](../08-usecase-specialized.md) |
| `e3-batch.py` | E3 大量バッチ処理(フロー図) | [08章 E3](../08-usecase-specialized.md) |
| `e4-media-gen.py` | E4 マルチモーダル生成(フロー図) | [08章 E4](../08-usecase-specialized.md) |
| `e5-m365-channels.py` | E5 Teams / M365 公開 | [08章 E5](../08-usecase-specialized.md) |
| `e6-finetune-ops.py` | E6 ファインチューニング運用ループ(フロー図) | [08章 E6](../08-usecase-specialized.md) |

## 図を作らないパターン(既存図から要素の増減のみで構成が変わらないため)

| パターン | 理由 |
|---|---|
| 公式-A Basic | 公式-B(`baseline-chat`)からネットワーク統制を引いただけ(PoC 専用・本番非推奨) |
| 公式-C ALZ 版 | 公式-B + hub-spoke。実装コードも記事から削除済み |
| A3 / A4 | A1 と同型のため `a1-prompt-rag-variants` に統合済み |
| C1 一般顧客向け(単一テナント) | C2 の単一テナント部分集合(公式-B + APIM + WAF チューニング) |
| C3 大規模・複数部門 | C2 の APIM キャパシティ・按分側面と同じ構成要素 |
| D2 Azure Government | A1 構成の Gov 版(機能制限が変わるだけ。hosted agent / MCP / A2A 非対応) |

## 新しい図を足すとき

1. 構成が近い既存スクリプトをコピーし、章の本文(ASCII 図・表)と乖離しないように描く
2. 生成 → PNG を目視確認(ラベル・エッジの重なり)→ 対象章に `![...](./images/<name>.png)` を挿入
3. `python3 docs/survey/tools/md2html.py` で HTML を再生成
