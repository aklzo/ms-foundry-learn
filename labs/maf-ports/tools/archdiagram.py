"""Pillow-based architecture-diagram helper (labs/maf-ports + docs/survey/architecture).

Why not graphviz: `dot` is not installable in this environment (no sudo), so
diagrams are composed manually with Pillow. Official Azure icons come from the
`diagrams` pip package (bundled under site-packages/resources/). Run scripts
with:

    uv run --with diagrams,pillow python <script.py>

Conventions (uniform across all diagrams):
  - Solid arrow  = data / control flow
  - Dashed arrow = telemetry (OTel -> App Insights)
  - Blue  text   = authentication (api-key / Entra ID / PAT)
  - Orange text  = billing / cost caution
  - Numbered badges (1, 2, 3 ...) on edges = the request flow, explained in a
    steps panel (`steps_panel`) so the picture reads without the prose
  - Status pills on nodes (`status="GA" | "Preview" | ...`) = service lifecycle
  - Clusters: "Local machine (uv + MAF)" | "Azure subscription > rg-maf-ports"
    (solid border) | external services (dashed border, outside Azure)
  - Bottom band: `notes()` (v2, tagged design points + Japanese legend) or the
    legacy `footer()` (English legend + free-form lines).

v2 (2026-09):
  - Japanese text: a CJK-capable font is auto-detected (Noto Sans CJK JP /
    Yu Gothic / Meiryo ...; override with ARCHDIAGRAM_FONT / ARCHDIAGRAM_FONT_BOLD).
    Without one, DejaVu is used and CJK text renders as boxes (a warning is printed).
  - Hi-DPI: everything is drawn at `scale` x (default 2, env ARCHDIAGRAM_SCALE).
    Scripts keep using logical (1x) coordinates; `d.d` is a scaling proxy.
  - `save(path, slide=...)` also writes a slide variant cropped to the diagram
    body (no title / subtitle / steps panel / bottom band) for embedding in Marp
    slides; the slide repeats the steps as HTML text.

Layout is manual: nodes are placed on a coarse grid via Diagram.gp(col, row)
or with raw pixel coordinates. 5-12 nodes per figure -> no auto-layout needed.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

# --- icon resolution ---------------------------------------------------------

import diagrams as _diagrams  # noqa: E402

ICON_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(_diagrams.__file__), "..", "resources")
)


def az(rel: str) -> str:
    """Path to an official Azure icon, e.g. az('aimachinelearning/ai-studio.png')."""
    return os.path.join(ICON_ROOT, "azure", rel)


def res(rel: str) -> str:
    """Path to any diagrams-bundled icon, e.g. res('onprem/vcs/github.png')."""
    return os.path.join(ICON_ROOT, rel)


# --- palette -----------------------------------------------------------------

INK = (33, 37, 41)
MUTED = (100, 106, 112)
BLUE = (0, 90, 158)        # auth
ORANGE = (196, 74, 12)     # billing / caution
RED = (180, 35, 45)        # hard constraint / not available
EDGE = (70, 70, 70)        # data flow
TELEM = (130, 130, 130)    # telemetry
GREEN = (16, 124, 65)
ACCENT = (15, 108, 189)    # step badges (same as the survey HTML --accent)

AZURE_BORDER = (90, 150, 210)
AZURE_FILL = (240, 246, 252)
LOCAL_BORDER = (130, 130, 130)
LOCAL_FILL = (248, 248, 248)
EXT_BORDER = (150, 150, 150)
EXT_FILL = (252, 252, 250)
SUB_BORDER = (160, 180, 200)
SUB_FILL = (250, 252, 254)
FOCUS_BORDER = (15, 108, 189)
FOCUS_FILL = (232, 242, 252)

BOX_FILL = (245, 248, 252)
BOX_BORDER = (91, 124, 166)

# status pill colours: (text, background)
STATUS_COLORS = {
    "GA": ((26, 127, 55), (218, 251, 225)),
    "Preview": ((154, 103, 0), (255, 243, 191)),
    "プレビュー": ((154, 103, 0), (255, 243, 191)),
    "Limited": ((130, 80, 223), (245, 235, 255)),
    "限定": ((130, 80, 223), (245, 235, 255)),
    "廃止予定": ((207, 34, 46), (255, 235, 233)),
    "Retiring": ((207, 34, 46), (255, 235, 233)),
    "自前": ((87, 96, 106), (234, 238, 242)),
}

# note tags for notes(): tag -> colour
TAG_COLORS = {
    "課金": ORANGE,
    "コスト": ORANGE,
    "認証": BLUE,
    "制約": RED,
    "閉域": (70, 80, 90),
    "運用": GREEN,
    "推奨": GREEN,
    "注意": ORANGE,
    "期限": RED,
    "実測": ACCENT,
}

# --- fonts -------------------------------------------------------------------

_HOME = os.path.expanduser("~")
_REGULAR_CANDIDATES = [
    (os.environ.get("ARCHDIAGRAM_FONT", ""), 0),
    (f"{_HOME}/.local/share/fonts/NotoSansCJKjp-Regular.otf", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", 0),
    ("/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf", 0),
    ("/mnt/c/Windows/Fonts/YuGothM.ttc", 0),
    ("/mnt/c/Windows/Fonts/meiryo.ttc", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
]
_BOLD_CANDIDATES = [
    (os.environ.get("ARCHDIAGRAM_FONT_BOLD", ""), 0),
    (f"{_HOME}/.local/share/fonts/NotoSansCJKjp-Bold.otf", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
    ("/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc", 0),
    ("/usr/share/fonts/truetype/noto/NotoSansCJKjp-Bold.otf", 0),
    ("/mnt/c/Windows/Fonts/YuGothB.ttc", 0),
    ("/mnt/c/Windows/Fonts/meiryob.ttc", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
]


def _first_existing(cands: list[tuple[str, int]]) -> tuple[str, int]:
    for path, idx in cands:
        if path and os.path.exists(path):
            return path, idx
    raise FileNotFoundError("no usable font found (install Noto Sans CJK JP or set ARCHDIAGRAM_FONT)")


_REG_PATH = _first_existing(_REGULAR_CANDIDATES)
_BOLD_PATH = _first_existing(_BOLD_CANDIDATES)
HAS_CJK = "DejaVu" not in _REG_PATH[0]


class LFont:
    """Logical font: `size` is in 1x (logical) pixels; `at(scale)` is the real face."""

    def __init__(self, bold: bool, size: int):
        self.bold = bold
        self.size = size
        self._cache: dict[float, ImageFont.FreeTypeFont] = {}

    def at(self, scale: float) -> ImageFont.FreeTypeFont:
        if scale not in self._cache:
            path, idx = _BOLD_PATH if self.bold else _REG_PATH
            self._cache[scale] = ImageFont.truetype(path, round(self.size * scale), index=idx)
        return self._cache[scale]


def font(size: int, bold: bool = False) -> LFont:
    return LFont(bold, size)


F_TITLE = font(23, bold=True)
F_SUB = font(14)
F_CLUSTER = font(15, bold=True)
F_LABEL = font(14)
F_LABEL_B = font(14, bold=True)
F_EDGE = font(12)
F_NOTE = font(13)
F_BOX = font(13)
F_STEP = font(12, bold=True)
F_PILL = font(10, bold=True)
F_PANEL = font(13)
F_PANEL_B = font(13, bold=True)

_CJK_RE = re.compile(r"[぀-ヿ一-鿿＀-￯]")


def _default_scale() -> float:
    try:
        return float(os.environ.get("ARCHDIAGRAM_SCALE", "2"))
    except ValueError:
        return 2.0


# --- scaling draw proxy --------------------------------------------------------


class ScaledDraw:
    """ImageDraw wrapper taking logical coordinates / LFont objects."""

    def __init__(self, img: Image.Image, scale: float):
        self._d = ImageDraw.Draw(img)
        self.s = scale

    def _xy(self, xy):
        s = self.s
        xy = list(xy)
        if xy and isinstance(xy[0], (int, float)):
            return [v * s for v in xy]
        return [(p[0] * s, p[1] * s) for p in xy]

    def _w(self, width) -> int:
        return max(1, round(width * self.s))

    def _f(self, f):
        return f.at(self.s) if isinstance(f, LFont) else f

    def line(self, xy, fill=None, width=1, **kw):
        self._d.line(self._xy(xy), fill=fill, width=self._w(width), **kw)

    def rectangle(self, xy, fill=None, outline=None, width=1):
        self._d.rectangle(self._xy(xy), fill=fill, outline=outline, width=self._w(width))

    def rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1):
        self._d.rounded_rectangle(
            self._xy(xy), radius=radius * self.s, fill=fill, outline=outline, width=self._w(width)
        )

    def ellipse(self, xy, fill=None, outline=None, width=1):
        self._d.ellipse(self._xy(xy), fill=fill, outline=outline, width=self._w(width))

    def polygon(self, xy, fill=None, outline=None):
        self._d.polygon(self._xy(xy), fill=fill, outline=outline)

    def arc(self, xy, start, end, fill=None, width=1):
        self._d.arc(self._xy(xy), start, end, fill=fill, width=self._w(width))

    def text(self, xy, text, font=None, fill=None, anchor=None, **kw):
        if not HAS_CJK and _CJK_RE.search(text or ""):
            _warn_cjk()
        self._d.text((xy[0] * self.s, xy[1] * self.s), text, font=self._f(font), fill=fill,
                     anchor=anchor, **kw)

    def textlength(self, text, font=None) -> float:
        return self._d.textlength(text, font=self._f(font)) / self.s


_warned = False


def _warn_cjk() -> None:
    global _warned
    if not _warned:
        print("warning: no CJK font found — Japanese labels will not render (set ARCHDIAGRAM_FONT)")
        _warned = True


# --- anchor-carrying shapes --------------------------------------------------


@dataclass
class Shape:
    """Anything with a rectangular footprint edges can attach to."""

    x0: float
    y0: float
    x1: float
    y1: float
    anchor_y: float | None = None  # nodes: icon centre (edges aim here, not at the label block)

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return self.anchor_y if self.anchor_y is not None else (self.y0 + self.y1) / 2

    def port(self, side: str, frac: float = 0.5) -> tuple[float, float]:
        """A point on one side: 'top'|'bottom'|'left'|'right'."""
        if side == "top":
            return (self.x0 + (self.x1 - self.x0) * frac, self.y0)
        if side == "bottom":
            return (self.x0 + (self.x1 - self.x0) * frac, self.y1)
        if side == "left":
            return (self.x0, self.y0 + (self.y1 - self.y0) * frac)
        if side == "right":
            return (self.x1, self.y0 + (self.y1 - self.y0) * frac)
        raise ValueError(side)

    def clip(self, ox: float, oy: float) -> tuple[float, float]:
        """Intersection of segment (center -> outside point) with this rect."""
        cx, cy = self.cx, self.cy
        dx, dy = ox - cx, oy - cy
        if dx == 0 and dy == 0:
            return (cx, cy)
        tx = abs(((self.x1 - cx) if dx > 0 else (cx - self.x0)) / dx) if dx else math.inf
        ty = abs(((self.y1 - cy) if dy > 0 else (cy - self.y0)) / dy) if dy else math.inf
        t = min(tx, ty)
        return (cx + dx * t, cy + dy * t)


# --- main canvas -------------------------------------------------------------


class Diagram:
    def __init__(
        self,
        title: str,
        width: int = 1400,
        height: int = 760,
        subtitle: str | None = None,
        cell: tuple[int, int] = (110, 100),
        origin: tuple[int, int] = (60, 110),
        scale: float | None = None,
    ):
        self.w, self.h = width, height
        self.s = scale or _default_scale()
        self.img = Image.new("RGB", (round(width * self.s), round(height * self.s)), "white")
        self.d = ScaledDraw(self.img, self.s)
        self.cell = cell
        self.origin = origin
        self._icon_cache: dict[tuple[str, int], Image.Image] = {}
        self._body: list[float] | None = None  # content bbox (everything but title and band)
        self._slide: list[float] | None = None  # slide-crop bbox (also excludes steps panels)
        self._in_panel = False
        self._band_top: float | None = None
        self._in_band = False
        self._shift: dict[int, float] = {}
        self.d.text((32, 22), title, font=F_TITLE, fill=INK)
        if subtitle:
            self.d.text((32, 56), subtitle, font=F_SUB, fill=MUTED)

    # grid -> pixel helper
    def gp(self, col: float, row: float) -> tuple[float, float]:
        return (self.origin[0] + col * self.cell[0], self.origin[1] + row * self.cell[1])

    def _grow(self, x0, y0, x1, y1) -> None:
        if self._in_band:
            return
        for name in (("_body",) if self._in_panel else ("_body", "_slide")):
            b = getattr(self, name)
            if b is None:
                setattr(self, name, [x0, y0, x1, y1])
            else:
                b[0], b[1], b[2], b[3] = min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)

    # -- primitives ----------------------------------------------------------

    def _dashed_line(self, p0, p1, fill, width=2, dash=7, gap=5):
        x0, y0 = p0
        x1, y1 = p1
        dist = math.hypot(x1 - x0, y1 - y0)
        if dist == 0:
            return
        n = int(dist // (dash + gap)) + 1
        vx, vy = (x1 - x0) / dist, (y1 - y0) / dist
        pos = 0.0
        for _ in range(n):
            a = (x0 + vx * pos, y0 + vy * pos)
            e = min(pos + dash, dist)
            b = (x0 + vx * e, y0 + vy * e)
            self.d.line([a, b], fill=fill, width=width)
            pos += dash + gap
            if pos >= dist:
                break

    def _dashed_rrect(self, rect, radius, outline, width=2):
        x0, y0, x1, y1 = rect
        # approximate: dash the 4 straight sides, draw solid small arcs
        self._dashed_line((x0 + radius, y0), (x1 - radius, y0), outline, width)
        self._dashed_line((x1, y0 + radius), (x1, y1 - radius), outline, width)
        self._dashed_line((x1 - radius, y1), (x0 + radius, y1), outline, width)
        self._dashed_line((x0, y1 - radius), (x0, y0 + radius), outline, width)
        self.d.arc([x0, y0, x0 + 2 * radius, y0 + 2 * radius], 180, 270, fill=outline, width=width)
        self.d.arc([x1 - 2 * radius, y0, x1, y0 + 2 * radius], 270, 360, fill=outline, width=width)
        self.d.arc([x1 - 2 * radius, y1 - 2 * radius, x1, y1], 0, 90, fill=outline, width=width)
        self.d.arc([x0, y1 - 2 * radius, x0 + 2 * radius, y1], 90, 180, fill=outline, width=width)

    def _ink_shift(self, font: LFont) -> float:
        """How far (logical px) a line's ink centre sits below the nominal line centre.

        CJK fonts carry a tall ascender, so text drawn at its top anchor looks low;
        subtracting this keeps labels centred in boxes whatever font was resolved."""
        key = id(font)
        if key not in self._shift:
            x0, y0, x1, y1 = self.d._d.textbbox((0, 0), "Ag漢", font=font.at(self.s), anchor="ma")
            self._shift[key] = max(0.0, (y0 + y1) / 2 / self.s - (font.size + 2) / 2)
        return self._shift[key]

    def _text_block(self, xy, lines, font, fill, anchor="mm", spacing=3, bg=None, grow=True):
        """Draw multiline text. anchor: 'mm' center x+y | 'ma' center x, top y | 'lt' left-top.

        Returns (top, bottom) y coordinates of the drawn block."""
        widths = [self.d.textlength(t, font=font) for t in lines]
        lh = font.size + spacing + 2
        total_h = lh * len(lines) - spacing
        w = max(widths) if widths else 0
        x, y = xy
        top = y - total_h / 2 if anchor == "mm" else y
        left = x - w / 2 if anchor in ("mm", "ma") else x
        if bg is not None:
            pad = 3
            self.d.rounded_rectangle(
                [left - pad, top - pad + 1, left + w + pad, top + total_h + pad], radius=3, fill=bg
            )
        shift = self._ink_shift(font)
        for i, t in enumerate(lines):
            ly = top + i * lh - shift
            if anchor in ("mm", "ma"):
                self.d.text((x, ly), t, font=font, fill=fill, anchor="ma")
            else:
                self.d.text((x, ly), t, font=font, fill=fill)
        if grow:
            self._grow(left, top, left + w, top + total_h)
        return top, top + total_h

    def _wrap(self, text: str, font: LFont, max_w: float) -> list[str]:
        """Greedy wrap that works for Japanese (per character) and English (per word)."""
        out: list[str] = []
        for para in text.split("\n"):
            tokens = re.findall(r"[A-Za-z0-9_./:+\-#%()'=\[\]<>@,]+ ?|.", para)
            line = ""
            for tok in tokens:
                if self.d.textlength(line + tok, font=font) <= max_w or not line:
                    line += tok
                else:
                    out.append(line.rstrip())
                    line = tok.lstrip()
            out.append(line.rstrip())
        return out

    # -- clusters ------------------------------------------------------------

    def cluster(
        self,
        x0,
        y0,
        x1,
        y1,
        label: str,
        kind: str = "azure",
        sublabel: str | None = None,
    ) -> Shape:
        """kind: 'azure' | 'local' | 'external' (dashed) | 'sub' (nested, lighter) | 'focus' (highlight)."""
        border, fill, dashed = {
            "azure": (AZURE_BORDER, AZURE_FILL, False),
            "local": (LOCAL_BORDER, LOCAL_FILL, False),
            "external": (EXT_BORDER, EXT_FILL, True),
            "sub": (SUB_BORDER, SUB_FILL, False),
            "focus": (FOCUS_BORDER, FOCUS_FILL, False),
        }[kind]
        if fill:
            self.d.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=fill)
        if dashed:
            self._dashed_rrect((x0, y0, x1, y1), 10, border, 2)
        else:
            self.d.rounded_rectangle([x0, y0, x1, y1], radius=10, outline=border, width=2)
        self.d.text((x0 + 12, y0 + 7), label, font=F_CLUSTER, fill=INK)
        if sublabel:
            lw = self.d.textlength(label, font=F_CLUSTER)
            self.d.text((x0 + 12 + lw + 10, y0 + 10), sublabel, font=F_EDGE, fill=MUTED)
        self._grow(x0, y0, x1, y1)
        return Shape(x0, y0, x1, y1)

    # -- nodes ---------------------------------------------------------------

    def _icon(self, path: str, size: int) -> Image.Image:
        key = (path, size)
        if key not in self._icon_cache:
            im = Image.open(path).convert("RGBA")
            px = round(size * self.s)
            im.thumbnail((px, px), Image.LANCZOS)
            self._icon_cache[key] = im
        return self._icon_cache[key]

    def pill(self, x: float, y: float, text: str, color=None, bg=None, anchor: str = "lm") -> Shape:
        """Small rounded status / tag pill. anchor 'lm' = left-middle, 'mm' = centre."""
        if color is None:
            color, bg2 = STATUS_COLORS.get(text, (MUTED, (234, 238, 242)))
            bg = bg or bg2
        bg = bg or (234, 238, 242)
        w = self.d.textlength(text, font=F_PILL) + 12
        h = F_PILL.size + 7
        x0 = x - w / 2 if anchor == "mm" else x
        y0 = y - h / 2
        self.d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=h / 2, fill=bg)
        self.d.text((x0 + w / 2, y0 + h / 2 + 0.5), text, font=F_PILL, fill=color, anchor="mm")
        self._grow(x0, y0, x0 + w, y0 + h)
        return Shape(x0, y0, x0 + w, y0 + h)

    def node(
        self,
        cx: float,
        cy: float,
        icon: str,
        label: str,
        icon_size: int = 64,
        label_color=INK,
        note: str | None = None,
        note_color=MUTED,
        status: str | None = None,
    ) -> Shape:
        """Icon centered at (cx, cy) with up to 2 label lines below.

        `note` adds one extra small line (use for auth / billing remarks).
        `status` draws a lifecycle pill (GA / Preview / ...) at the icon's upper right."""
        im = self._icon(icon, icon_size)
        iw, ih = im.size[0] / self.s, im.size[1] / self.s
        self.img.paste(im, (round((cx - iw / 2) * self.s), round((cy - ih / 2) * self.s)), im)
        self._grow(cx - iw / 2, cy - ih / 2, cx + iw / 2, cy + ih / 2)
        lines = label.split("\n")[:2]
        _, bottom = self._text_block(
            (cx, cy + ih / 2 + 5), lines, F_LABEL, label_color, anchor="ma"
        )
        if note:
            self._text_block((cx, bottom + 4), [note], F_EDGE, note_color, anchor="ma")
            bottom += 4 + F_EDGE.size + 2
        if status:
            self.pill(cx + iw / 2 - 6, cy - ih / 2 + 2, status)
        return Shape(cx - iw / 2, cy - ih / 2, cx + iw / 2, bottom, anchor_y=cy)

    def box(
        self,
        cx: float,
        cy: float,
        w: float,
        h: float,
        label: str,
        fill=BOX_FILL,
        border=BOX_BORDER,
        font=F_BOX,
        text_color=INK,
        status: str | None = None,
    ) -> Shape:
        """Small labelled box (workflow stage etc.). Label may be multiline."""
        x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        self.d.rounded_rectangle([x0, y0, x1, y1], radius=7, fill=fill, outline=border, width=2)
        self._grow(x0, y0, x1, y1)
        self._text_block((cx, cy), label.split("\n"), font, text_color, anchor="mm")
        if status:
            self.pill(x1 - 8, y0, status, anchor="mm")
        return Shape(x0, y0, x1, y1)

    def text(self, x: float, y: float, text: str, font: LFont = F_EDGE, fill=MUTED,
             anchor: str = "lt") -> tuple[float, float]:
        """Free text (multiline) that counts toward the slide crop. anchor 'lt' | 'ma' | 'mm'."""
        return self._text_block((x, y), text.split("\n"), font, fill, anchor=anchor)

    # -- step badges ------------------------------------------------------------

    def step(self, n: int | str, x: float, y: float, r: float = 11, color=ACCENT) -> Shape:
        """Numbered flow badge (filled circle). Explain the numbers with steps_panel()."""
        self.d.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=(255, 255, 255), width=2)
        self.d.text((x, y + 0.5), str(n), font=F_STEP, fill=(255, 255, 255), anchor="mm")
        self._grow(x - r, y - r, x + r, y + r)
        return Shape(x - r, y - r, x + r, y + r)

    def steps_panel(
        self,
        x0: float,
        y0: float,
        x1: float,
        items: list[str],
        title: str = "処理の流れ",
        start: int = 1,
        numbers: list[str] | None = None,
        columns: int = 1,
    ) -> Shape:
        """Panel listing the numbered steps (badge + wrapped text). Returns its Shape.

        columns > 1 lays the items out row-major in that many columns (use it for a wide,
        short panel under the diagram). The panel is left out of the slide crop — slides
        show the same steps as HTML text (bigger), so put the panel at the bottom."""
        self._in_panel = True
        pad = 12
        gap = 18
        lh = F_PANEL.size + 6
        col_w = (x1 - x0 - pad * 2 - gap * (columns - 1)) / columns
        rows: list[tuple[str, list[str]]] = []
        for i, item in enumerate(items):
            num = numbers[i] if numbers else str(start + i)
            rows.append((num, self._wrap(item, F_PANEL, col_w - 30)))
        grid = [rows[i:i + columns] for i in range(0, len(rows), columns)]
        row_h = [max(len(r[1]) for r in g) * lh + 6 for g in grid]
        h = pad + F_PANEL_B.size + 10 + sum(row_h) + pad - 6
        self.d.rounded_rectangle([x0, y0, x1, y0 + h], radius=10,
                                 fill=(255, 255, 255), outline=(205, 214, 224), width=1)
        self.d.text((x0 + pad, y0 + pad - 2), title, font=F_PANEL_B, fill=INK)
        y = y0 + pad + F_PANEL_B.size + 10
        for g, rh in zip(grid, row_h):
            for ci, (num, lines) in enumerate(g):
                cx = x0 + pad + ci * (col_w + gap)
                self.step(num, cx + 10, y + lh / 2 - 1, r=10)
                for j, ln in enumerate(lines):
                    self.d.text((cx + 28, y + j * lh), ln, font=F_PANEL, fill=INK)
            y += rh
        self._grow(x0, y0, x1, y0 + h)
        self._in_panel = False
        return Shape(x0, y0, x1, y0 + h)

    # -- edges ---------------------------------------------------------------

    def _arrow_head(self, tip, angle, color, size=9):
        a1 = angle + math.radians(153)
        a2 = angle - math.radians(153)
        p1 = (tip[0] + size * math.cos(a1), tip[1] + size * math.sin(a1))
        p2 = (tip[0] + size * math.cos(a2), tip[1] + size * math.sin(a2))
        self.d.polygon([tip, p1, p2], fill=color)

    def edge(
        self,
        a,
        b,
        label: str | None = None,
        style: str = "solid",
        color=EDGE,
        label_color=None,
        route: str = "straight",
        label_t: float = 0.5,
        label_dy: float | None = None,
        label_dx: float | None = None,
        width: int = 2,
        arrow: bool = True,
        via: list[tuple[float, float]] | None = None,
        step: int | str | None = None,
        both: bool = False,
        label_pos: str = "right",
    ):
        """Arrow a -> b. a/b: Shape or (x, y).

        style: 'solid' (data) | 'dashed' (telemetry).
        route: 'straight' | 'hv' (horizontal then vertical) | 'vh'.
        via: explicit waypoint list (overrides route).
        step: numbered badge placed on the line at label_t; the label then sits beside it
              (label_pos: 'right' | 'left' | 'above' | 'below'; label_dx/dy nudge it further).
        both: arrow heads on both ends (request/response pair).
        Blue label => auth, orange label => billing (pass label_color)."""
        pa = (a.cx, a.cy) if isinstance(a, Shape) else a
        pb = (b.cx, b.cy) if isinstance(b, Shape) else b

        if via:
            p0 = a.clip(*via[0]) if isinstance(a, Shape) else pa
            p1 = b.clip(*via[-1]) if isinstance(b, Shape) else pb
            pts = [p0, *via, p1]
        elif route == "straight":
            p0 = a.clip(*pb) if isinstance(a, Shape) else pa
            p1 = b.clip(*pa) if isinstance(b, Shape) else pb
            pts = [p0, p1]
        else:
            if route == "hv":
                corner = (pb[0], pa[1])
            else:
                corner = (pa[0], pb[1])
            p0 = a.clip(*corner) if isinstance(a, Shape) else pa
            p1 = b.clip(*corner) if isinstance(b, Shape) else pb
            pts = [p0, corner, p1]

        for s, e in zip(pts, pts[1:]):
            if style == "dashed":
                self._dashed_line(s, e, color, width)
            else:
                self.d.line([s, e], fill=color, width=width)
        if arrow:
            s, e = pts[-2], pts[-1]
            self._arrow_head(e, math.atan2(e[1] - s[1], e[0] - s[0]), color)
            if both:
                s, e = pts[1], pts[0]
                self._arrow_head(e, math.atan2(e[1] - s[1], e[0] - s[0]), color)

        if label or step is not None:
            # place along the full polyline at fraction label_t
            seglens = [math.hypot(e[0] - s[0], e[1] - s[1]) for s, e in zip(pts, pts[1:])]
            total = sum(seglens) or 1
            target = total * label_t
            acc = 0.0
            lx, ly = pts[-1]
            for (s, e), L in zip(zip(pts, pts[1:]), seglens):
                if acc + L >= target:
                    f = (target - acc) / L if L else 0
                    lx = s[0] + (e[0] - s[0]) * f
                    ly = s[1] + (e[1] - s[1]) * f
                    break
                acc += L
            if step is not None:
                self.step(step, lx, ly)
                if label:
                    lines = label.split("\n")
                    bh = (F_EDGE.size + 5) * len(lines) - 3
                    bw = max(self.d.textlength(t, font=F_EDGE) for t in lines)
                    ox, oy = label_dx or 0, label_dy or 0
                    if label_pos == "left":
                        xy, anc = (lx - 14 - bw + ox, ly - bh / 2 + oy), "lt"
                    elif label_pos == "above":
                        xy, anc = (lx + ox, ly - 15 - bh + oy), "ma"
                    elif label_pos == "below":
                        xy, anc = (lx + ox, ly + 15 + oy), "ma"
                    else:
                        xy, anc = (lx + 14 + ox, ly - bh / 2 + oy), "lt"
                    self._text_block(xy, lines, F_EDGE, label_color or color, anchor=anc, bg=(255, 255, 255))
            else:
                self._text_block(
                    (lx + (label_dx or 0), ly + (-10 if label_dy is None else label_dy)),
                    label.split("\n"),
                    F_EDGE,
                    label_color or color,
                    anchor="mm",
                    bg=(255, 255, 255),
                )

    # -- bottom bands --------------------------------------------------------

    def _legend_row(self, y: float, ja: bool, config_note: str | None, source: str | None):
        lx = 32.0
        labels = (
            ("データ・制御", "テレメトリ(OTel)", "認証", "課金・コスト注意")
            if ja else ("data / control", "telemetry (OTel)", "auth", "billing note")
        )
        self.d.line([lx, y + 7, lx + 34, y + 7], fill=EDGE, width=2)
        self._arrow_head((lx + 34, y + 7), 0, EDGE, 7)
        self.d.text((lx + 42, y), labels[0], font=F_EDGE, fill=INK)
        lx += 50 + self.d.textlength(labels[0], font=F_EDGE) + 18
        self._dashed_line((lx, y + 7), (lx + 34, y + 7), TELEM, 2)
        self._arrow_head((lx + 34, y + 7), 0, TELEM, 7)
        self.d.text((lx + 42, y), labels[1], font=F_EDGE, fill=INK)
        lx += 50 + self.d.textlength(labels[1], font=F_EDGE) + 18
        self.d.text((lx, y), labels[2], font=F_EDGE, fill=BLUE)
        lx += self.d.textlength(labels[2], font=F_EDGE) + 18
        self.d.text((lx, y), labels[3], font=F_EDGE, fill=ORANGE)
        lx += self.d.textlength(labels[3], font=F_EDGE) + 26
        if ja:
            self.step(1, lx + 8, y + 8, r=9)
            self.d.text((lx + 22, y), "処理順", font=F_EDGE, fill=INK)
            lx += 22 + self.d.textlength("処理順", font=F_EDGE) + 18
            p = self.pill(lx, y + 8, "GA")
            p2 = self.pill(p.x1 + 4, y + 8, "Preview")
            self.d.text((p2.x1 + 6, y), "ステータス", font=F_EDGE, fill=INK)
            lx = p2.x1 + 6 + self.d.textlength("ステータス", font=F_EDGE) + 24
        tail = config_note if config_note is not None else (
            None if ja else
            "Lab config: public endpoints, no VNet (closed-network variant: docs/survey/architecture/07)"
        )
        if tail:
            self.d.text((lx, y), tail, font=F_EDGE, fill=MUTED)
        if source:
            self.d.text((self.w - 32, y), source, font=F_EDGE, fill=MUTED, anchor="ra")

    def footer(
        self,
        notes: list[str],
        auth: list[str] | None = None,
        config_note: str | None = None,
    ):
        """Legacy bottom band: English legend row + config note + notes + auth summary.

        notes lines starting with '$' are drawn orange (billing), '@' blue (auth).
        config_note overrides the default lab-config caption (used by the
        docs/survey diagrams, which are not lab configurations)."""
        band_lines = len(notes) + (len(auth) if auth else 0)
        band_h = 46 + band_lines * 20
        y0 = self.h - band_h
        self._band_top = y0
        self._in_band = True
        self.d.rectangle([0, y0, self.w, self.h], fill=(245, 245, 245))
        self.d.line([0, y0, self.w, y0], fill=(210, 210, 210), width=1)
        self._legend_row(y0 + 13, ja=False, config_note=config_note, source=None)
        ty = y0 + 38
        for line in notes:
            color = INK
            if line.startswith("$"):
                color, line = ORANGE, line[1:]
            elif line.startswith("@"):
                color, line = BLUE, line[1:]
            self.d.text((32, ty), line, font=F_NOTE, fill=color)
            ty += 20
        if auth:
            for line in auth:
                self.d.text((32, ty), line, font=F_NOTE, fill=BLUE)
                ty += 20
        self._in_band = False

    def notes(
        self,
        points: list[tuple[str, str]],
        source: str | None = None,
        config_note: str | None = None,
        columns: int = 1,
    ) -> None:
        """v2 bottom band: Japanese legend row + tagged design points.

        points: [(tag, text)] where tag is one of TAG_COLORS (課金 / 認証 / 制約 / 閉域 / 運用 / 推奨 / 注意 /
        期限 / 実測) or any short word. Keep it to 3-5 points; the prose belongs in the Markdown."""
        pad_x = 32
        col_w = (self.w - pad_x * 2 - (columns - 1) * 24) / columns
        lh = F_NOTE.size + 7
        wrapped = []
        for tag, text in points:
            tw = self.d.textlength(tag, font=F_PILL) + 12
            wrapped.append((tag, tw, self._wrap(text, F_NOTE, col_w - tw - 10)))
        per_col = math.ceil(len(wrapped) / columns) if wrapped else 0
        cols = [wrapped[i * per_col:(i + 1) * per_col] for i in range(columns)]
        col_h = [sum(len(w[2]) * lh + 5 for w in c) for c in cols]
        band_h = 40 + (max(col_h) if col_h else 0) + 10
        # the band goes right under the drawn body: the canvas height follows the content
        y0 = (self._body[3] if self._body else self.h - band_h) + 22
        self._resize(y0 + band_h)
        self._band_top = y0
        self._in_band = True
        self.d.rectangle([0, y0, self.w, self.h], fill=(246, 247, 249))
        self.d.line([0, y0, self.w, y0], fill=(214, 219, 225), width=1)
        self._legend_row(y0 + 12, ja=True, config_note=config_note, source=source)
        for ci, col in enumerate(cols):
            x = pad_x + ci * (col_w + 24)
            y = y0 + 38
            for tag, tw, lines in col:
                color = TAG_COLORS.get(tag, MUTED)
                light = tuple(int(c + (255 - c) * 0.86) for c in color)
                self.pill(x, y + lh / 2 - 2, tag, color=color, bg=light)
                for j, ln in enumerate(lines):
                    self.d.text((x + tw + 10, y + j * lh), ln, font=F_NOTE, fill=INK)
                y += len(lines) * lh + 5
        self._in_band = False

    def _resize(self, new_h: float) -> None:
        """Change the logical canvas height (keeps the drawn pixels from the top)."""
        new_h = round(new_h)
        if new_h == self.h:
            return
        img = Image.new("RGB", (self.img.size[0], round(new_h * self.s)), "white")
        img.paste(self.img.crop((0, 0, self.img.size[0], min(self.img.size[1], img.size[1]))), (0, 0))
        self.img, self.h = img, new_h
        self.d = ScaledDraw(self.img, self.s)

    # -- output ----------------------------------------------------------------

    def save(self, path: str, slide: str | None = None, margin: int = 14):
        """Write the full figure; with `slide`, also write the body-only crop for slides."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.img.save(path, optimize=True)
        print(f"wrote {path} ({self.img.size[0]}x{self.img.size[1]}, scale {self.s:g})")
        if slide:
            b = self._slide or self._body or [0, 0, self.w, self.h]
            bottom = b[3] + margin
            if self._band_top is not None:
                bottom = min(bottom, self._band_top - 1)
            box = (
                max(0, round((b[0] - margin) * self.s)),
                max(0, round((b[1] - margin) * self.s)),
                min(self.img.size[0], round((b[2] + margin) * self.s)),
                min(self.img.size[1], round(bottom * self.s)),
            )
            os.makedirs(os.path.dirname(slide) or ".", exist_ok=True)
            crop = self.img.crop(box)
            crop.save(slide, optimize=True)
            print(f"wrote {slide} ({crop.size[0]}x{crop.size[1]})")


# --- standard icon shorthand (the ledger) ------------------------------------

ICONS = {
    "foundry": az("aimachinelearning/ai-studio.png"),          # Foundry (AIServices) account
    "project": az("aimachinelearning/machine-learning.png"),   # Foundry project
    "model": az("aimachinelearning/azure-openai.png"),         # model deployment
    "search": az("appservices/cognitive-search.png"),          # Azure AI Search
    "appinsights": az("devops/application-insights.png"),      # Application Insights
    "loganalytics": az("analytics/log-analytics-workspaces.png"),
    "entra": az("identity/azure-active-directory.png"),        # Entra ID
    "rbac": az("identity/azure-ad-roles-and-administrators.png"),  # role assignments
    "mi": az("identity/managed-identities.png"),               # managed identity
    "cli": az("general/dev-console.png"),                      # local CLI / MAF app
    "browser": az("general/browser.png"),                      # external web API
    "files": az("general/files.png"),                          # Files API
    "cache": az("general/cache.png"),                          # Memory store
    "container": az("compute/container-instances.png"),        # sandbox container
    "containerapp": az("compute/container-apps.png"),          # hosted agent container
    "scheduler": az("general/scheduler.png"),                  # Routines
    "speech": az("aimachinelearning/speech-services.png"),     # Voice Live
    "evals": az("devops/test-plans.png"),                      # cloud evals
    "workflow": az("general/workflow.png"),                    # MAF workflow
    "keys": az("menu/keys.png"),                               # api-key
    "github": res("onprem/vcs/github.png"),                    # GitHub (non-Azure)
    "user": res("onprem/client/user.png"),                     # end user
}


def icon(name: str) -> str:
    return ICONS[name]


# --- standard "shared Azure backdrop" for port diagrams ----------------------


def std_azure(
    d: Diagram,
    x0: int = 780,
    y0: int = 100,
    x1: int = 1360,
    y1: int = 665,
    base: str = "mafports",
    rg: str = "rg-maf-ports",
    model_note: str = "GlobalStandard, capacity 10",
    foundry_h: int = 300,
    ja: bool = False,
) -> dict[str, Shape]:
    """Shared-infra backdrop used by every port diagram: Azure subscription
    cluster > Foundry account (project + gpt-5.4-mini) + App Insights +
    Log Analytics. Returns shapes: azure, foundry, project, model, appi, logw.
    ja=True uses Japanese captions (v2 diagrams)."""
    azc = d.cluster(
        x0, y0, x1, y1,
        f"Azure サブスクリプション — {rg}(Japan East)" if ja else f"Azure subscription — {rg} (Japan East)",
        kind="azure",
    )
    fc = d.cluster(
        x0 + 30, y0 + 50, x1 - 30, y0 + 50 + foundry_h,
        f"Foundry: aif-{base}", kind="sub",
        sublabel="共有基盤(AIServices S0)" if ja else "shared infra (AIServices S0)",
    )
    mx = (x0 + x1) / 2
    ny = y0 + 50 + foundry_h * 0.42
    model = d.node(mx - 145, ny, icon("model"), "モデルデプロイ\ngpt-5.4-mini" if ja else "Model deployment\ngpt-5.4-mini",
                   note=model_note, status="GA" if ja else None)
    project = d.node(mx + 145, ny, icon("project"), "プロジェクト: maf-ports" if ja else "Project: maf-ports",
                     note="システム割り当て MI" if ja else "system MI")
    appi = d.node(mx - 145, y1 - 108, icon("appinsights"), "App Insights\nappi-" + base)
    logw = d.node(mx + 145, y1 - 108, icon("loganalytics"), "Log Analytics\nlog-" + base)
    d.edge(appi, logw)
    return {"azure": azc, "foundry": fc, "project": project, "model": model, "appi": appi, "logw": logw}


NOTE_SHARED_ONLY = (
    "Infra: shared foundation only — infra/main.bicep holds existing references + outputs "
    "(no port-specific Azure resources)."
)
NOTE_SHARED_ONLY_JA = "インフラは共有基盤のみ — infra/main.bicep は既存リソース参照と出力だけ(ポート固有の Azure リソースなし)"
