#!/usr/bin/env python3
"""Markdown (生成AI用・正) から HTML (人間用) を生成する共有ビルドスクリプト。

使い方:
    python3 docs/survey/tools/md2html.py                # 全ドキュメントセットをビルド
    python3 docs/survey/tools/md2html.py architecture   # 指定セットのみビルド

docs/survey/<セット>/*.md を読み込み、docs/survey/<セット>/html/ に HTML を出力する。
README.md は index.html になる。標準ライブラリのみ使用。

対応しているMarkdownサブセット:
  見出し(h1-h4) / 段落 / 箇条書き(1段ネスト) / 番号付きリスト / テーブル /
  フェンスコードブロック / 引用 / 水平線 / **強調** / `コード` / [リンク](url)

テーブルセル先頭のステータス語 (GA / パブリックプレビュー / 非推奨 など) は
バッジ表示に変換される。.md へのリンクは .html に書き換えられる
(他セットへの `../features/xx.md` 形式も `../../features/html/xx.html` に追従)。
"""

from __future__ import annotations

import html as html_mod
import re
import sys
from pathlib import Path

SURVEY_DIR = Path(__file__).resolve().parent.parent
DOC_SETS = ["features", "architecture", "proposal"]

# セル先頭にあるときバッジ化するステータス語 (長い語を先に)
BADGE_CLASSES = [
    ("パブリックプレビュー", "preview"),
    ("プライベートプレビュー", "private"),
    ("限定プレビュー", "private"),
    ("プレビュー", "preview"),
    ("Preview", "preview"),
    ("preview", "preview"),
    ("GA", "ga"),
    ("ベータ", "beta"),
    ("beta", "beta"),
    ("非推奨予定", "deprecated"),
    ("非推奨", "deprecated"),
    ("廃止済み", "retired"),
    ("廃止", "retired"),
    ("要確認", "unknown"),
    ("記載なし", "na"),
    ("対応", "ok"),
    ("未対応", "no"),
    ("推奨", "ga"),
    ("条件付き", "preview"),
    ("不可", "no"),
]
_BADGE_RE = re.compile(
    r"^(\s*)(" + "|".join(re.escape(t) for t, _ in BADGE_CLASSES) + r")(?=$|[\s(（/、,:：。→])"
)
_BADGE_MAP = dict(BADGE_CLASSES)

CSS = """
:root {
  --bg: #ffffff; --fg: #1c1e21; --muted: #57606a; --border: #d8dee4;
  --accent: #0f6cbd; --code-bg: #f3f5f7; --nav-bg: #f7f9fb;
  --ga: #1a7f37; --ga-bg: #dafbe1; --preview: #9a6700; --preview-bg: #fff8c5;
  --dep: #cf222e; --dep-bg: #ffebe9; --unk: #57606a; --unk-bg: #eef1f4;
  --priv: #8250df; --priv-bg: #fbefff;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161a1e; --fg: #e6e8ea; --muted: #9aa4ae; --border: #3a4149;
    --accent: #62aaf0; --code-bg: #22272d; --nav-bg: #1d2227;
    --ga: #4ecb71; --ga-bg: #16321d; --preview: #e8bd4e; --preview-bg: #3a3016;
    --dep: #ff7b72; --dep-bg: #3c1f1e; --unk: #a8b3bd; --unk-bg: #2a3138;
    --priv: #c297ff; --priv-bg: #2f2440;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font-family: "Segoe UI", "Hiragino Sans", "Noto Sans JP", Meiryo, sans-serif;
  font-size: 15px; line-height: 1.75;
}
nav.site {
  background: var(--nav-bg); border-bottom: 1px solid var(--border);
  padding: 0.5rem 1.2rem; display: flex; flex-wrap: wrap; gap: 0.2rem 1.1rem;
  font-size: 0.85rem; position: sticky; top: 0; z-index: 10;
}
nav.site a { color: var(--muted); text-decoration: none; padding: 0.15rem 0; }
nav.site a:hover { color: var(--accent); }
nav.site a.current { color: var(--accent); font-weight: 600; }
nav.site a.xset { color: var(--muted); opacity: 0.75; font-style: italic; }
main { max-width: 1100px; margin: 0 auto; padding: 1.5rem 1.2rem 4rem; }
h1 { font-size: 1.7rem; line-height: 1.35; border-bottom: 2px solid var(--border); padding-bottom: 0.4rem; }
h2 { font-size: 1.3rem; margin-top: 2.2rem; border-bottom: 1px solid var(--border); padding-bottom: 0.25rem; }
h3 { font-size: 1.1rem; margin-top: 1.8rem; }
h4 { font-size: 1rem; margin-top: 1.4rem; }
a { color: var(--accent); }
code {
  background: var(--code-bg); border-radius: 4px; padding: 0.1em 0.4em;
  font-family: Consolas, "SF Mono", Menlo, monospace; font-size: 0.86em;
}
pre {
  background: var(--code-bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 0.9rem 1rem; overflow-x: auto; line-height: 1.45;
}
pre code { background: none; padding: 0; font-size: 0.82em; }
blockquote {
  margin: 1rem 0; padding: 0.5rem 1rem; border-left: 4px solid var(--accent);
  background: var(--nav-bg); border-radius: 0 6px 6px 0; color: var(--muted);
}
.tablewrap { overflow-x: auto; margin: 1rem 0; }
table { border-collapse: collapse; width: 100%; font-size: 0.88rem; line-height: 1.55; }
th, td {
  border: 1px solid var(--border); padding: 0.45rem 0.6rem;
  text-align: left; vertical-align: top; min-width: 4.5em;
}
th { background: var(--nav-bg); white-space: nowrap; }
tr:nth-child(even) td { background: color-mix(in srgb, var(--nav-bg) 40%, transparent); }
.badge {
  display: inline-block; font-size: 0.78rem; font-weight: 600; line-height: 1.4;
  padding: 0 0.5em; border-radius: 999px; white-space: nowrap;
}
.badge.ga { color: var(--ga); background: var(--ga-bg); }
.badge.preview, .badge.beta { color: var(--preview); background: var(--preview-bg); }
.badge.private { color: var(--priv); background: var(--priv-bg); }
.badge.deprecated, .badge.retired, .badge.no { color: var(--dep); background: var(--dep-bg); }
.badge.unknown, .badge.na { color: var(--unk); background: var(--unk-bg); }
.badge.ok { color: var(--ga); background: var(--ga-bg); }
.toc {
  background: var(--nav-bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 0.8rem 1.2rem; margin: 1.2rem 0; font-size: 0.9rem;
}
.toc strong { display: block; margin-bottom: 0.3rem; }
.toc ul { margin: 0; padding-left: 1.2rem; columns: 2; column-gap: 2rem; }
@media (max-width: 700px) { .toc ul { columns: 1; } }
footer {
  max-width: 1100px; margin: 0 auto; padding: 0 1.2rem 2rem;
  color: var(--muted); font-size: 0.8rem;
}
"""


def slugify(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^\w぀-ヿ一-鿿-]+", "-", text.strip())
    return text.strip("-").lower() or "section"


_BARE_URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'*+,;=%()]+")


def _autolink(m: re.Match) -> str:
    """ベアURLをリンク化。表示テキストはパス末尾のスラッグに短縮する。"""
    url = m.group(0).rstrip(".,;:)]")
    trail = m.group(0)[len(url):]
    path = url.split("://", 1)[1].rstrip("/")
    slug = path.split("/")[-1].split("?")[0].split("#")[0] or path
    if len(slug) <= 2:
        slug = path
    return f'<a href="{url}" title="{url}">{slug}</a>{trail}'


def inline(text: str) -> str:
    """インライン要素の変換 (エスケープ → コード保護 → リンク → 強調)。"""
    codes: list[str] = []

    def stash(m: re.Match) -> str:
        codes.append(f"<code>{html_mod.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html_mod.escape(text, quote=False)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: f'<a href="{fix_link(m.group(2))}">{m.group(1)}</a>',
        text,
    )
    # 既存の <a href="..."> を保護してから、残ったベアURLをリンク化
    anchors: list[str] = []

    def stash_a(m: re.Match) -> str:
        anchors.append(m.group(0))
        return f"\x01{len(anchors) - 1}\x01"

    text = re.sub(r"<a [^>]*>.*?</a>", stash_a, text)
    text = _BARE_URL_RE.sub(_autolink, text)
    text = re.sub(r"\x01(\d+)\x01", lambda m: anchors[int(m.group(1))], text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def fix_link(url: str) -> str:
    """.md リンクを html/ 内の .html リンクへ書き換える。

    同ディレクトリ:      ./03-x.md            -> 03-x.html
    他ドキュメントセット: ../features/03-x.md  -> ../../features/html/03-x.html
    """
    if url.startswith(("http://", "https://", "#", "mailto:")):
        return url
    m = re.match(r"^\.\./([\w.-]+)/([\w.-]+)\.md(#.*)?$", url)
    if m and m.group(1) in DOC_SETS:
        name = "index" if m.group(2) == "README" else m.group(2)
        return f"../../{m.group(1)}/html/{name}.html{m.group(3) or ''}"
    m = re.match(r"^(?:\./)?([\w.-]+)\.md(#.*)?$", url)
    if m:
        name = "index" if m.group(1) == "README" else m.group(1)
        return f"{name}.html{m.group(2) or ''}"
    return url


def badge_cell(cell: str) -> str:
    m = _BADGE_RE.match(cell)
    if not m:
        return cell
    cls = _BADGE_MAP[m.group(2)]
    rest = cell[m.end():]
    return f'{m.group(1)}<span class="badge {cls}">{m.group(2)}</span>{rest}'


def convert(md: str) -> tuple[str, str, list[tuple[str, str]]]:
    """Markdown本文 → (HTML, タイトル, [(h2テキスト, id)])"""
    lines = md.split("\n")
    out: list[str] = []
    title = ""
    h2s: list[tuple[str, str]] = []
    i = 0
    in_list: list[str] = []  # 開いているリストタグのスタック

    def close_lists(depth: int = 0) -> None:
        while len(in_list) > depth:
            out.append(f"</{in_list.pop()}>")

    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            close_lists()
            block: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            out.append(f"<pre><code>{html_mod.escape(chr(10).join(block))}</code></pre>")
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            close_lists()
            level = len(m.group(1))
            text = inline(m.group(2))
            hid = slugify(m.group(2))
            if level == 1 and not title:
                title = re.sub(r"<[^>]+>", "", text)
            if level == 2:
                h2s.append((text, hid))
            out.append(f'<h{level} id="{hid}">{text}</h{level}>')
            i += 1
            continue

        if re.match(r"^\s*\|.*\|\s*$", line) and i + 1 < len(lines) and re.match(
            r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]
        ):
            close_lists()
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            rows: list[list[str]] = []
            i += 2
            while i < len(lines) and re.match(r"^\s*\|.*\|\s*$", lines[i]):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append('<div class="tablewrap"><table><thead><tr>')
            out.extend(f"<th>{inline(c)}</th>" for c in header)
            out.append("</tr></thead><tbody>")
            for row in rows:
                out.append("<tr>")
                out.extend(f"<td>{badge_cell(inline(c))}</td>" for c in row)
                out.append("</tr>")
            out.append("</tbody></table></div>")
            continue

        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            depth = 1 + (1 if len(m.group(1)) >= 2 else 0)
            tag = "ol" if m.group(2)[0].isdigit() else "ul"
            if len(in_list) < depth:
                out.append(f"<{tag}>")
                in_list.append(tag)
            elif len(in_list) > depth:
                close_lists(depth)
            out.append(f"<li>{inline(m.group(3))}</li>")
            i += 1
            continue

        if re.match(r"^\s*(---+|\*\*\*+)\s*$", line):
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        if line.startswith(">"):
            close_lists()
            quote: list[str] = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(inline(lines[i].lstrip("> ")))
                i += 1
            out.append(f"<blockquote><p>{'<br>'.join(quote)}</p></blockquote>")
            continue

        if not line.strip():
            close_lists()
            i += 1
            continue

        close_lists()
        para = [line]
        while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(
            r"^(#{1,4}\s|```|\s*\||\s*[-*]\s|\s*\d+\.\s|>|\s*---)", lines[i + 1]
        ):
            i += 1
            para.append(lines[i])
        out.append(f"<p>{inline(' '.join(para))}</p>")
        i += 1

    close_lists()
    return "\n".join(out), title, h2s


def short(title: str) -> str:
    """ナビ用の短縮タイトル (長い説明を除去)。"""
    t = re.sub(r"\s*[—–|:：(（].*$", "", title)
    return t if len(t) <= 26 else t[:25] + "…"


def build_set(set_name: str, other_sets: list[str]) -> bool:
    src_dir = SURVEY_DIR / set_name
    if not src_dir.is_dir():
        return False
    md_files = sorted(src_dir.glob("*.md"), key=lambda p: (p.name != "README.md", p.name))
    if not md_files:
        return False

    out_dir = src_dir / "html"
    pages = []  # (md_path, html名, タイトル)
    parsed = {}
    for p in md_files:
        body, title, h2s = convert(p.read_text(encoding="utf-8"))
        html_name = "index.html" if p.name == "README.md" else p.stem + ".html"
        pages.append((p, html_name, title or p.stem))
        parsed[p] = (body, title or p.stem, h2s)

    xset_nav = "".join(
        f'<a class="xset" href="../../{s}/html/index.html">→ {s}</a>'
        for s in other_sets
        if (SURVEY_DIR / s / "html" / "index.html").exists() or (SURVEY_DIR / s).is_dir()
    )

    out_dir.mkdir(exist_ok=True)
    for p, html_name, _ in pages:
        body, title, h2s = parsed[p]
        nav = "".join(
            f'<a href="{hn}"{" class=\"current\"" if hn == html_name else ""}>{short(t)}</a>'
            for _, hn, t in pages
        )
        toc = ""
        if len(h2s) >= 3:
            items = "".join(f'<li><a href="#{hid}">{t}</a></li>' for t, hid in h2s)
            toc = f'<div class="toc"><strong>このページの内容</strong><ul>{items}</ul></div>'
        # h1直後にTOCを挿入
        if toc:
            body = re.sub(r"(</h1>)", r"\1" + toc, body, count=1)
        doc = (
            "<!DOCTYPE html>\n"
            '<html lang="ja"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{title}</title>\n<style>{CSS}</style></head>\n"
            f'<body><nav class="site">{nav}{xset_nav}</nav>\n<main>\n{body}\n</main>\n'
            f"<footer>このHTMLは docs/survey/{set_name}/*.md から "
            "docs/survey/tools/md2html.py で自動生成されています。編集はMarkdown側で行ってください。</footer>"
            "</body></html>\n"
        )
        (out_dir / html_name).write_text(doc, encoding="utf-8")
        print(f"  {set_name}/{p.name} -> {set_name}/html/{html_name}")
    return True


def main(argv: list[str]) -> int:
    targets = argv[1:] or DOC_SETS
    unknown = [t for t in targets if t not in DOC_SETS]
    if unknown:
        print(f"unknown doc set(s): {', '.join(unknown)}  (known: {', '.join(DOC_SETS)})")
        return 1
    print(f"build: {SURVEY_DIR}")
    built = 0
    for name in targets:
        if build_set(name, [s for s in DOC_SETS if s != name]):
            built += 1
        else:
            print(f"  skip: {name} (ディレクトリまたは .md が存在しない)")
    print(f"done ({built} set(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
