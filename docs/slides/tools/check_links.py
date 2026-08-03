#!/usr/bin/env python3
"""スライド MD 内の相対リンク・画像パスの存在を検証する(標準ライブラリのみ)。

Marp は md2html.py と違いリンクの書き換えをしないため、MD に書いた相対パスが
生成 HTML でもそのまま使われる。ここでは docs/slides/ 基準で参照先ファイルの
存在だけを確認する(http/https/#/mailto は対象外)。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: check_links.py <slides.md>")
        return 1
    md_path = Path(argv[1]).resolve()
    base = md_path.parent
    text = md_path.read_text(encoding="utf-8")
    text = re.sub(r"```.*?```", "", text, flags=re.S)  # コードブロック内は対象外

    missing: list[str] = []
    checked = 0
    targets = [m.group(1) for m in re.finditer(r"\]\(([^)\s]+)\)", text)]
    targets += [m.group(2) for m in re.finditer(r'(href|src)="([^"]+)"', text)]
    for url in targets:
        if url.startswith(("http://", "https://", "#", "mailto:", "data:")):
            continue
        path = url.split("#", 1)[0]
        if not path:
            continue
        checked += 1
        if not (base / path).exists():
            missing.append(url)

    if missing:
        print(f"NG: リンク切れ {len(missing)} 件")
        for url in missing:
            print(f"  - {url}")
        return 1
    print(f"OK: 相対リンク {checked} 件すべて存在")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
