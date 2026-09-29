#!/usr/bin/env python3
"""labs の実行ガイド(runbook)を Markdown(正)から HTML(人間の確認用)へ生成する。

使い方(リポジトリルートで):
    python3 labs/tools/build_runbooks.py           # 全 runbook と索引をビルド
    python3 labs/tools/build_runbooks.py --check   # HTML が Markdown と同期しているか検証(差分があれば exit 1)

対象:
    labs/**/docs/runbook.md  -> 同じディレクトリの runbook.html
    labs/runbooks.md         -> labs/runbooks.html(全 runbook の索引)

Markdown の変換器は docs/survey/tools/md2html.py を共有する(サブセットも同じ)。
runbook 固有の拡張:
  - タスクリスト `- [ ] 項目` と表セル `[ ]` をチェックボックスにする
    (チェック状態はブラウザの localStorage にページ単位で保存。確認作業の途中経過用)
  - リンク書き換え: 他の runbook.md → runbook.html、docs/survey/<set>/*.md → 生成済み HTML。
    それ以外の .md(ポートの README など)はそのまま残す
  - 画像は Markdown と同じディレクトリ基準のまま(HTML を md と同階層に出力するため)
"""

from __future__ import annotations

import html as html_mod
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LABS = REPO / "labs"
INDEX_MD = LABS / "runbooks.md"
SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}

sys.path.insert(0, str(REPO / "docs" / "survey" / "tools"))
import md2html  # noqa: E402

EXTRA_CSS = """
nav.site .grp { color: var(--muted); font-weight: 600; opacity: 0.8; }
.task { list-style: none; margin-left: -1.3rem; }
input.chk { width: 1.05rem; height: 1.05rem; vertical-align: -0.15rem; margin-right: 0.35rem; accent-color: var(--accent); }
td.chk-cell { text-align: center; min-width: 2.5em; width: 2.5em; }
.progress {
  position: sticky; top: 2.6rem; z-index: 5; float: right; margin: 0 0 0.8rem 1rem;
  background: var(--nav-bg); border: 1px solid var(--border); border-radius: 999px;
  padding: 0.15rem 0.8rem; font-size: 0.82rem; color: var(--muted);
}
.progress button {
  margin-left: 0.5rem; font: inherit; font-size: 0.78rem; color: var(--accent);
  background: none; border: none; cursor: pointer; padding: 0;
}
@media print { nav.site, .progress { display: none; } }
"""

CHECK_JS = """
<script>
(function () {
  var boxes = Array.prototype.slice.call(document.querySelectorAll('input.chk'));
  if (!boxes.length) return;
  var key = 'runbook:' + location.pathname;
  var state = {};
  try { state = JSON.parse(localStorage.getItem(key) || '{}'); } catch (e) { state = {}; }
  var bar = document.createElement('div');
  bar.className = 'progress';
  var main = document.querySelector('main');
  main.insertBefore(bar, main.firstChild);
  function render() {
    var n = boxes.filter(function (b) { return b.checked; }).length;
    bar.innerHTML = '確認済み ' + n + ' / ' + boxes.length + '<button type="button">リセット</button>';
    bar.querySelector('button').onclick = function () {
      boxes.forEach(function (b) { b.checked = false; });
      save(); render();
    };
  }
  function save() {
    var s = {};
    boxes.forEach(function (b, i) { if (b.checked) s[i] = 1; });
    try { localStorage.setItem(key, JSON.stringify(s)); } catch (e) { /* 保存不可の環境では表示のみ */ }
  }
  boxes.forEach(function (b, i) {
    b.checked = !!state[i];
    b.addEventListener('change', function () { save(); render(); });
  });
  render();
})();
</script>
"""


def find_runbooks() -> list[Path]:
    found: list[Path] = []
    for root, dirs, files in os.walk(LABS):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        if "runbook.md" in files and Path(root).name == "docs":
            found.append(Path(root) / "runbook.md")
    return sorted(found)


def html_path(md: Path) -> Path:
    return md.with_suffix(".html")


def make_link_fixer(md_file: Path, runbooks: set[Path]):
    base = md_file.parent

    def fix_link(url: str) -> str:
        if url.startswith(("http://", "https://", "#", "mailto:")):
            return url
        path_part, _, frag = url.partition("#")
        frag = f"#{frag}" if frag else ""
        if not path_part.endswith(".md"):
            return url
        target = (base / path_part).resolve()
        if target in runbooks or target == INDEX_MD.resolve():
            return os.path.relpath(html_path(target), base) + frag
        try:
            rel = target.relative_to(REPO / "docs" / "survey")
        except ValueError:
            return url
        if len(rel.parts) == 2 and rel.parts[0] in md2html.DOC_SETS:
            name = "index" if rel.stem == "README" else rel.stem
            out = REPO / "docs" / "survey" / rel.parts[0] / "html" / f"{name}.html"
            return os.path.relpath(out, base) + frag
        return url

    return fix_link


def checkboxes(body: str) -> str:
    body = re.sub(
        r"<li>\[([ xX])\]\s*",
        lambda m: '<li class="task"><input type="checkbox" class="chk"'
        + (" checked" if m.group(1) != " " else "")
        + "> ",
        body,
    )
    return re.sub(
        r"<td>\[([ xX])\]</td>",
        lambda m: '<td class="chk-cell"><input type="checkbox" class="chk"'
        + (" checked" if m.group(1) != " " else "")
        + "></td>",
        body,
    )


def label_for(md: Path) -> tuple[str, str]:
    """(グループ名, 項目名) — ナビ表示用。"""
    rel = md.relative_to(LABS).parts
    if rel[0] == "maf-ports" and len(rel) > 2 and rel[1] == "ports":
        return "maf-ports", rel[2]
    if rel[0] == "maf-ports" and rel[1] == "infra":
        return "maf-ports", "共有基盤"
    return "labs", rel[0]


def render(md: Path, runbooks: list[Path]) -> str:
    md2html.fix_link = make_link_fixer(md, {p.resolve() for p in runbooks})
    md2html.fix_img = lambda url: url
    body, title, h2s = md2html.convert(md.read_text(encoding="utf-8"))
    body = checkboxes(body)
    if len(h2s) >= 3:
        items = "".join(f'<li><a href="#{hid}">{t}</a></li>' for t, hid in h2s)
        toc = f'<div class="toc"><strong>このページの内容</strong><ul>{items}</ul></div>'
        body = re.sub(r"(</h1>)", r"\1" + toc, body, count=1)

    here = md.parent
    nav_parts = [f'<a href="{os.path.relpath(LABS / "runbooks.html", here)}"'
                 + (' class="current"' if md == INDEX_MD else "") + ">索引</a>"]
    group = None
    for p in runbooks:
        g, name = label_for(p)
        if g != group:
            nav_parts.append(f'<span class="grp">{g}:</span>')
            group = g
        cls = ' class="current"' if p == md else ""
        nav_parts.append(f'<a href="{os.path.relpath(html_path(p), here)}"{cls}>{name}</a>')
    src = md.relative_to(REPO).as_posix()
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ja"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html_mod.escape(title or md.stem)}</title>\n"
        f"<style>{md2html.CSS}{EXTRA_CSS}</style></head>\n"
        f'<body><nav class="site">{"".join(nav_parts)}</nav>\n<main>\n{body}\n</main>\n'
        f"<footer>この HTML は {src} から labs/tools/build_runbooks.py で自動生成されています。"
        "編集は Markdown 側で行ってください。</footer>"
        f"{CHECK_JS}</body></html>\n"
    )


def main(argv: list[str]) -> int:
    check = "--check" in argv[1:]
    runbooks = find_runbooks()
    targets = runbooks + ([INDEX_MD] if INDEX_MD.exists() else [])
    stale: list[str] = []
    for md in targets:
        out = html_path(md)
        doc = render(md, runbooks)
        rel = out.relative_to(REPO).as_posix()
        if check:
            if not out.exists() or out.read_text(encoding="utf-8") != doc:
                stale.append(rel)
            continue
        out.write_text(doc, encoding="utf-8")
        print(f"  {md.relative_to(REPO).as_posix()} -> {rel}")
    if check:
        if stale:
            print("HTML が Markdown と同期していない(build_runbooks.py を実行してください):")
            print("\n".join(f"  {s}" for s in stale))
            return 1
        print(f"ok: {len(targets)} 件の HTML は Markdown と同期している")
        return 0
    print(f"done ({len(targets)} file(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
