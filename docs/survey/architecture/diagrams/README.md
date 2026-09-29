# diagrams — アーキテクチャ図の生成

`../images/*.png`(survey HTML 用)と `../images/slide/*.png`(スライド用の切り出し版)は、本ディレクトリの
Python スクリプトから同時に生成する。描画ヘルパーは
[labs/maf-ports/tools/archdiagram.py](../../../../labs/maf-ports/tools/archdiagram.py)
(Pillow 自前合成。公式 Azure アイコンは `diagrams` pip パッケージ同梱のものを使用)を共有する。
規約(実線=データ/破線=テレメトリ/青=認証/橙=課金注意)は
[maf-ports 側の README](../../../../labs/maf-ports/tools/README.md) に従う。

## v2 スタイル(2026-09-29〜)

- **日本語ラベル**(サービス名・製品名は公式の英語表記のまま)。日本語フォントはヘルパーが自動検出
  (Noto Sans CJK JP / Yu Gothic / Meiryo。`ARCHDIAGRAM_FONT` で上書き可)。見つからないと DejaVu になり日本語が豆腐になる(警告が出る)
- **2 倍解像度**(`ARCHDIAGRAM_SCALE`、既定 2)。スクリプトの座標は 1 倍の論理座標のまま
- **処理番号**: 主要な流れのエッジに `step=N` の青丸番号+図の下端に「処理の流れ」パネル(`steps_panel(columns=2〜3)`)
- **ステータスバッジ**: Foundry 機能のノードに `status="GA" / "Preview"` 等(値は features の MD が正。推測で付けない)
- **注記帯**: 旧来の英文 `footer()` をやめ、`notes([(タグ, 文), ...])` の 3〜5 行(タグ = 課金 / 認証 / 制約 / 閉域 / 運用 / 推奨 / 注意 / 期限 / 実測)。
  長い説明は本文(Markdown)に書き、図には判断に効く要点だけを残す
- **スライド用切り出し**: `d.save(images/<name>.png, slide=images/slide/<name>.png)`。スライド版はタイトル・処理の流れパネル・注記帯を除いた本体のみ
  (スライド側で処理番号の説明を HTML で大きく書くため)。処理の流れパネルは必ず本体の**下端に全幅で**置く
- 見本: [b2-hitl-automation.py](./b2-hitl-automation.py)

## 再生成

```bash
# リポジトリルートで
for f in docs/survey/architecture/diagrams/*.py; do
  uv run --with diagrams,pillow python "$f"
done
```

PNG は `docs/survey/architecture/images/`(+ スライド用は `images/slide/`)に上書き出力される。Markdown には
`![...](./images/<name>.png)` で埋め込み、HTML は `md2html.py` が `../images/` 参照へ自動書き換える。
スライド(`docs/slides/`)は `images/slide/<name>.png` を全幅で使う。

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

1. 構成が近い既存スクリプト(v2 スタイルのもの)をコピーし、章の本文(ASCII 図・表)と乖離しないように描く
2. 生成 → **本体とスライド版の両方の PNG** を目視確認(ラベル・エッジ・アイコンの重なり、偏った余白)→ 対象章に `![...](./images/<name>.png)` を挿入
3. `python3 docs/survey/tools/md2html.py` で HTML を再生成。スライドで使うなら `docs/slides/` の要点列(処理番号の説明)も同期
