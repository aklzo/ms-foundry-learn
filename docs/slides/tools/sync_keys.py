#!/usr/bin/env python3
"""スライドの「処理番号の説明(.keys)」をアーキ図スクリプトの処理の流れパネルから同期する。

アーキ図(docs/survey/architecture/diagrams/<name>.py)の `steps_panel([...])` に書いた手順文を、
スライド MD の `data-keys` 付きブロックへ `.keys` の HTML として書き出す。図とスライドで番号の説明がずれない。

    <div class="keys" data-keys="b2-hitl-automation"></div>     ← 新しく置くときはこの 1 行だけ書く
    ↓ 同期後(ブロックの中身は自動生成。手で編集しない)
    <div class="keys rows2" data-keys="b2-hitl-automation">
    <div class="k"><span class="n">1</span>…</div>
    </div>

(Marp は HTML コメントを発表者ノートとして扱うため、マーカーにはコメントを使わない)

使い方(build.sh からも呼ばれる):
    python3 docs/slides/tools/sync_keys.py            # 書き換え
    python3 docs/slides/tools/sync_keys.py --check    # 差分があれば exit 1
標準ライブラリのみ。
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SLIDES = HERE.parent / "foundry-si-overview.md"
DIAGRAMS = HERE.parents[1] / "survey" / "architecture" / "diagrams"

# 空のブロック(初回)と、.k 行を持つブロック(2 回目以降)の両方に一致させる
_BLOCK = re.compile(
    r'<div class="keys[^"]*" data-keys="([\w.-]+)">(?:</div>|\n(?:<div class="k">.*</div>\n)*</div>)'
)


def steps_of(name: str) -> list[tuple[str, str]]:
    """[(番号, 手順文)]。steps_panel の numbers= / start= 指定(A, B, 1, 2 … など)も反映する。"""
    tree = ast.parse((DIAGRAMS / f"{name}.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "steps_panel":
            kw = {k.arg: k.value for k in node.keywords}
            lst = node.args[3] if len(node.args) > 3 else kw["items"]
            items = [ast.literal_eval(e) for e in lst.elts]
            if "numbers" in kw:
                nums = [str(n) for n in ast.literal_eval(kw["numbers"])]
            else:
                start = ast.literal_eval(kw["start"]) if "start" in kw else 1
                nums = [str(start + i) for i in range(len(items))]
            return list(zip(nums, items))
    raise ValueError(f"{name}.py に steps_panel がない")


def render(name: str) -> str:
    items = steps_of(name)
    cls = "keys rows2" if len(items) >= 5 else "keys"
    rows = "\n".join(f'<div class="k"><span class="n">{n}</span>{t}</div>' for n, t in items)
    return f'<div class="{cls}" data-keys="{name}">\n{rows}\n</div>'


def main(argv: list[str]) -> int:
    src = SLIDES.read_text(encoding="utf-8")
    out = _BLOCK.sub(lambda m: render(m.group(1)), src)
    names = _BLOCK.findall(src)
    if "--check" in argv[1:]:
        if out != src:
            print("スライドの処理番号の説明が図と同期していない(sync_keys.py を実行してください)")
            return 1
        print(f"ok: {len(names)} 枚のスライドの処理番号が図と同期している")
        return 0
    if out != src:
        SLIDES.write_text(out, encoding="utf-8")
    print(f"synced: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
