#!/usr/bin/env python3
"""後方互換シム。実体は docs/survey/tools/md2html.py に移動した(共有ビルダー)。

このスクリプトは features セットのみをビルドする。
architecture も含めて全部ビルドする場合は共有ビルダーを直接呼ぶこと:

    python3 docs/survey/tools/md2html.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))

from md2html import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main([sys.argv[0], "features"]))
