# tools — アーキテクチャ図の生成

各ポートの `docs/architecture.png` と共有基盤の `infra/docs/architecture.png` は、
[archdiagram.py](./archdiagram.py)(Pillow 自前合成ヘルパー)を使う Python スクリプト
(`*/docs/architecture.py`)から生成する。

## 前提と手段

- **graphviz(dot)は使わない**(この環境では sudo 不可でインストールできない)。Pillow で矩形・矢印・テキストを直接描画する
- 公式 Azure アイコン PNG は **`diagrams` pip パッケージ同梱**のものを使う(`site-packages/resources/azure/` 配下。GitHub アイコン等は `resources/onprem/` などから)。パスは実行時に `import diagrams` から解決するのでパッケージの場所に依存しない
- フォントは DejaVu(`/usr/share/fonts/truetype/dejavu/`)。**日本語グリフが無いため図中テキストは英語**
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

## 図の規約(全 13 枚で統一。ヘルパーが実装)

| 要素 | 規約 |
| --- | --- |
| クラスタ | `Local machine (uv + MAF)` / `Azure subscription — rg-... (Japan East)` / 外部サービスは**破線枠**(Azure 外)。Foundry アカウントは Azure 内の入れ子クラスタ |
| ノード | 公式アイコン 64px + 下ラベル最大 2 行(+小さい補足 1 行)。ワークフロー段は小ボックス列 |
| エッジ | **実線=データ/制御**、**破線=テレメトリ(OTel → App Insights)**。中間ラベル付き |
| 色 | **青=認証**(api-key / Entra ID / PAT / MI)、**橙=課金・コスト注意** |
| 注記帯 | 下部の帯に凡例+ `Lab config: public endpoints, no VNet (closed-network variant: docs/survey/architecture/07)` +接続ごとの認証方式一覧(青)+課金注意(橙) |
| レイアウト | 手動座標(ノード 5〜10 個なので自動レイアウト不要)。`Diagram.gp(col,row)` のグリッド補助あり |

主なアイコン対応(`archdiagram.ICONS`): Foundry=`aimachinelearning/ai-studio`、プロジェクト=`aimachinelearning/machine-learning`、モデルデプロイ=`aimachinelearning/azure-openai`、AI Search=`appservices/cognitive-search`、App Insights=`devops/application-insights`、Log Analytics=`analytics/log-analytics-workspaces`、Memory=`general/cache`、Code Interpreter=`compute/container-instances`、hosted agent=`compute/container-apps`、Routines=`general/scheduler`、Voice Live=`aimachinelearning/speech-services`、評価=`devops/test-plans`、CLI=`general/dev-console`、外部 Web=`general/browser`、GitHub=`onprem/vcs/github`。

## 新しいポートの図を足すとき

1. `ports/<port>/docs/architecture.py` を既存ポート(構成が近いもの)からコピー
2. `std_azure()` で共有基盤バックドロップを敷き、固有リソース・エッジを足す(README と infra/main.bicep の内容から乖離させないこと)
3. 生成 → PNG を目視確認(ラベル・エッジの重なり)→ README の「移植後の構成」節に `![architecture](./docs/architecture.png)` を挿入
