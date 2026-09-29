# tools — アーキテクチャ図の生成

各ポートの `docs/architecture.png` と共有基盤の `infra/docs/architecture.png` は、
[archdiagram.py](./archdiagram.py)(Pillow 自前合成ヘルパー)を使う Python スクリプト
(`*/docs/architecture.py`)から生成する。

## 前提と手段

- **graphviz(dot)は使わない**(この環境では sudo 不可でインストールできない)。Pillow で矩形・矢印・テキストを直接描画する
- 公式 Azure アイコン PNG は **`diagrams` pip パッケージ同梱**のものを使う(`site-packages/resources/azure/` 配下。GitHub アイコン等は `resources/onprem/` などから)。パスは実行時に `import diagrams` から解決するのでパッケージの場所に依存しない
- フォントは日本語対応フォントを自動検出(`~/.local/share/fonts/NotoSansCJKjp-*.otf` → `/usr/share/fonts` の Noto CJK → WSL なら Windows 側の Yu Gothic / Meiryo → 最後に DejaVu)。`ARCHDIAGRAM_FONT` / `ARCHDIAGRAM_FONT_BOLD` で明示指定可。DejaVu しか無い環境では日本語が表示できない(警告が出る)。Noto Sans CJK JP は sudo 不要で `~/.local/share/fonts/` に置けば使える
- 出力は 2 倍解像度(`ARCHDIAGRAM_SCALE` で変更可)。スクリプトは 1 倍の論理座標で書く(`d.d` は座標を拡大する描画プロキシ)
- 依存はスクリプト実行時に `uv run --with diagrams,pillow` で都度解決(各ポートの venv を汚さない)

## 再生成

```bash
cd labs/maf-ports

# 全図(共有基盤 + 12 ポート)
for f in $(find . -name architecture.py -path '*/docs/*'); do
  uv run --with diagrams,pillow python "$f"
done

# 1 枚だけ
uv run --with diagrams,pillow python ports/corrective-rag/docs/architecture.py
```

PNG はスクリプトと同じ `docs/` ディレクトリに上書き出力される。

## 図の規約(ヘルパーが実装。2026-09-29 に v2 — 日本語・処理番号・ステータスバッジ・日本語注記帯を追加。旧 API は互換のまま)

| 要素 | 規約 |
| --- | --- |
| クラスタ | `Local machine (uv + MAF)` / `Azure subscription — rg-... (Japan East)` / 外部サービスは**破線枠**(Azure 外)。Foundry アカウントは Azure 内の入れ子クラスタ |
| ノード | 公式アイコン 64px + 下ラベル最大 2 行(+小さい補足 1 行)。ワークフロー段は小ボックス列 |
| エッジ | **実線=データ/制御**、**破線=テレメトリ(OTel → App Insights)**。中間ラベル付き |
| 色 | **青=認証**(api-key / Entra ID / PAT / MI)、**橙=課金・コスト注意** |
| 注記帯 | v2: `notes([(タグ, 文), ...])` — 日本語の凡例行+タグ付きの要点 3〜5 行(タグ = 課金 / 認証 / 制約 / 閉域 / 運用 / 推奨 / 注意 / 期限 / 実測)。帯は本体の直下に自動配置され、キャンバスの高さは内容に追従する。旧 `footer()`(英語の凡例+自由記述行)も引き続き使える |
| 処理番号 | v2: 主要な流れのエッジに `edge(..., step=N)`(青丸番号)+本体の下端に `steps_panel([...], columns=2〜3)` |
| ステータス | v2: `node(..., status="GA")` / `"Preview"` / `"限定"` / `"廃止予定"` でノード右上にバッジ |
| スライド版 | v2: `save(path, slide=...)` でタイトル・処理の流れパネル・注記帯を除いた本体の切り出しも出力 |
| レイアウト | 手動座標(ノード 5〜10 個なので自動レイアウト不要)。`Diagram.gp(col,row)` のグリッド補助あり |

主なアイコン対応(`archdiagram.ICONS`): Foundry=`aimachinelearning/ai-studio`、プロジェクト=`aimachinelearning/machine-learning`、モデルデプロイ=`aimachinelearning/azure-openai`、AI Search=`appservices/cognitive-search`、App Insights=`devops/application-insights`、Log Analytics=`analytics/log-analytics-workspaces`、Memory=`general/cache`、Code Interpreter=`compute/container-instances`、hosted agent=`compute/container-apps`、Routines=`general/scheduler`、Voice Live=`aimachinelearning/speech-services`、評価=`devops/test-plans`、CLI=`general/dev-console`、外部 Web=`general/browser`、GitHub=`onprem/vcs/github`。

## 新しいポートの図を足すとき

1. `ports/<port>/docs/architecture.py` を既存ポート(構成が近いもの)からコピー
2. `std_azure()` で共有基盤バックドロップを敷き、固有リソース・エッジを足す(README と infra/main.bicep の内容から乖離させないこと)
3. 生成 → PNG を目視確認(ラベル・エッジの重なり)→ README の「移植後の構成」節に `![architecture](./docs/architecture.png)` を挿入
