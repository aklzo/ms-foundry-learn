#!/usr/bin/env bash
# docs/slides のビルド: Markdown(正)→ HTML / PDF + 相対リンク検証
#
# 使い方:
#   bash docs/slides/build.sh              # HTML + PDF + リンク検証
#   SKIP_PDF=1 bash docs/slides/build.sh   # HTML のみ(執筆中の高速プレビュー用)
#
# PDF 変換には WSL 内の chrome-headless-shell を使う(sudo 不要)。初回のみ:
#   npx -y puppeteer browsers install chrome-headless-shell@stable
# ※ Windows 側 Chrome は WSL2 の NAT モードだとデバッグポートに接続できず使えない。
# 日本語フォントが WSL に無い場合は Windows 側フォントを fontconfig 経由で参照する。
set -euo pipefail
cd "$(dirname "$0")"

if [[ -z "${CHROME_PATH:-}" ]]; then
  shell_bin=$(ls -1 "$HOME"/.cache/puppeteer/chrome-headless-shell/*/chrome-headless-shell-linux64/chrome-headless-shell 2>/dev/null | sort -V | tail -1 || true)
  if [[ -n "$shell_bin" ]]; then
    export CHROME_PATH="$shell_bin"
  elif [[ "${SKIP_PDF:-}" != "1" ]]; then
    echo "PDF 用ブラウザが未導入。次を実行してから再ビルド:" >&2
    echo "  npx -y puppeteer browsers install chrome-headless-shell@stable" >&2
    exit 1
  fi
fi

if ! fc-list :lang=ja 2>/dev/null | grep -q . && [[ -d /mnt/c/Windows/Fonts ]]; then
  export FONTCONFIG_FILE="$(pwd)/tools/fonts.conf"
fi

MARP=(npx -y @marp-team/marp-cli@4.5.0 --theme-set themes/si-foundry.css --html --allow-local-files)

"${MARP[@]}" foundry-si-overview.md -o foundry-si-overview.html
echo "built: foundry-si-overview.html"

if [[ "${SKIP_PDF:-}" != "1" ]]; then
  "${MARP[@]}" --pdf --pdf-notes foundry-si-overview.md -o foundry-si-overview.pdf
  echo "built: foundry-si-overview.pdf"
fi

python3 tools/check_links.py foundry-si-overview.md
