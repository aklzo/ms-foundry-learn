# docs/slides — SI チーム向け共有スライド

> **最終更新:** 2026-08-03 / **版:** 初版(勉強会 2026-08 向け)

課内 SI チーム向けの勉強会スライド(45 分想定+後日参照)。本リポジトリの調査資産(survey 3 セット+tech-selection-guide+labs)の**入口(1 層目)**として、「持ち帰る 3 つの判断能力」(決める順序 / 当たりの付け方 / 見積もりの現実)を軸に本編 34 枚+付録 4 枚へ再構成したもの。詳細は各スライド下部のリンクから survey の HTML(2 層目)へ降りる設計。

## ファイル構成

| ファイル | 役割 |
| --- | --- |
| `foundry-si-overview.md` | スライド本体(Marp 形式)。**これが正**。スピーカーノートは HTML コメントで記載 |
| `themes/si-foundry.css` | カスタムテーマ。配色は `docs/survey/tools/md2html.py` の CSS 変数から移植(survey HTML と同一ブランド) |
| `build.sh` | ビルド(HTML+PDF+リンク検証) |
| `tools/check_links.py` | MD 内の相対リンク・画像・`href`/`src` の存在チェック(標準ライブラリのみ) |
| `tools/fonts.conf` | WSL に日本語フォントが無い環境向けに Windows 側フォントを参照する fontconfig |
| `foundry-si-overview.html` | 生成物(コミットする)。ブラウザで開くとスライド表示。`p` キーでプレゼンタービュー(ノート表示) |
| `foundry-si-overview.pdf` | 生成物(コミットする)。配布用。ノートは PDF 注釈として埋め込み |

## ビルド

```bash
bash docs/slides/build.sh              # HTML + PDF + リンク検証
SKIP_PDF=1 bash docs/slides/build.sh   # HTML のみ(執筆中の高速プレビュー)
```

- 前提: node / npx(marp-cli は npx で自動取得)。**PDF 変換は初回のみ** `npx -y puppeteer browsers install chrome-headless-shell@stable` で WSL 内にブラウザを導入(sudo 不要)
- WSL2(NAT モード)では Windows 側 Chrome をデバッグ接続できないため、WSL 内の chrome-headless-shell を使う。日本語フォントは `tools/fonts.conf` 経由で Windows 側フォント(Yu Gothic 等)を参照する
- **HTML / PDF は直接編集しない**(md2html.py と同じ原則。編集は Markdown 側で)

## 設計メモ

- **出力を `html/` に分けず MD と同階層に置く**: Marp は md2html.py と違いリンクパスを書き換えないため、MD と出力の階層を揃えることで `../survey/architecture/html/*.html` という相対リンクが MD 編集時・HTML 閲覧時の両方で有効になる
- **リンクの二重化**: PDF を単体配布するとファイルリンクは切れるため、「詳細へ」導線はクリック可能リンク+可視のリポジトリパス表記のセットで書く
- **CJK 太字の罠**: `**...(HITL)**が` のように**全角約物の直後で太字を閉じて直後に文字が続く**と CommonMark の規則でパースされない。太字の境界は語の内側に置く(閉じ `**` の直前を文字にする)
- 図は `docs/survey/architecture/images/*.png` を流用(図中テキストは英語。再生成は `diagrams/*.py`)
- 発表日はタイトルスライドと本 README の更新履歴に持たせ、ファイル名には入れない(改訂・再演に耐える)

## 更新方針

- survey の大型更新(Ignite 11 月・Build 5 月の直後)に合わせて内容を改訂する。特に**期限表(スライド 24・付録 A3)と GA/プレビュー状況(スライド 6)は陳腐化が速い**
- PDF はビルドごとではなく**内容改訂時のみ再生成してコミット**(バイナリ差分の膨張を避ける)

## 更新履歴

| 日付 | 内容 |
| --- | --- |
| 2026-08-03 | 初版。本編 34 枚+付録 4 枚(パターン完全版 / やってくれないこと 12 項 / 期限全体表 / Copilot Studio 境界) |
