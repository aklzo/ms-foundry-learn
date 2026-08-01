"""Pillow-based architecture-diagram helper for labs/maf-ports.

Why not graphviz: `dot` is not installable in this environment (no sudo), so
diagrams are composed manually with Pillow. Official Azure icons come from the
`diagrams` pip package (bundled under site-packages/resources/). Run scripts
with:

    uv run --with diagrams,pillow python <script.py>

Conventions (uniform across all port diagrams):
  - Solid arrow  = data / control flow
  - Dashed arrow = telemetry (OTel -> App Insights)
  - Blue  text   = authentication (api-key / Entra ID / PAT)
  - Orange text  = billing / cost caution
  - Clusters: "Local machine (uv + MAF)" | "Azure subscription > rg-maf-ports"
    (solid border) | external services (dashed border, outside Azure)
  - Bottom note band: lab network assumption + per-connection auth summary.

Text in diagrams is English only (DejaVu fonts carry no CJK glyphs).

Layout is manual: nodes are placed on a coarse grid via Diagram.gp(col, row)
or with raw pixel coordinates. 5-10 nodes per figure -> no auto-layout needed.
"""

from __future__ import annotations

import math
import os
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


# --- palette / fonts ---------------------------------------------------------

INK = (40, 40, 40)
MUTED = (110, 110, 110)
BLUE = (0, 90, 158)        # auth
ORANGE = (196, 74, 12)     # billing / caution
EDGE = (70, 70, 70)        # data flow
TELEM = (130, 130, 130)    # telemetry
GREEN = (16, 124, 65)

AZURE_BORDER = (90, 150, 210)
AZURE_FILL = (240, 246, 252)
LOCAL_BORDER = (130, 130, 130)
LOCAL_FILL = (248, 248, 248)
EXT_BORDER = (150, 150, 150)
EXT_FILL = (252, 252, 250)
SUB_BORDER = (160, 180, 200)
SUB_FILL = (250, 252, 254)

BOX_FILL = (245, 248, 252)
BOX_BORDER = (91, 124, 166)

_FONT_DIR = "/usr/share/fonts/truetype/dejavu"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(_FONT_DIR, name), size)


F_TITLE = _font("DejaVuSans-Bold.ttf", 22)
F_SUB = _font("DejaVuSans.ttf", 14)
F_CLUSTER = _font("DejaVuSans-Bold.ttf", 15)
F_LABEL = _font("DejaVuSans.ttf", 14)
F_LABEL_B = _font("DejaVuSans-Bold.ttf", 14)
F_EDGE = _font("DejaVuSans.ttf", 12)
F_NOTE = _font("DejaVuSans.ttf", 13)
F_BOX = _font("DejaVuSans.ttf", 13)


# --- anchor-carrying shapes --------------------------------------------------


@dataclass
class Shape:
    """Anything with a rectangular footprint edges can attach to."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

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
        tx = abs((self.x1 - self.x0) / 2 / dx) if dx else math.inf
        ty = abs((self.y1 - self.y0) / 2 / dy) if dy else math.inf
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
    ):
        self.w, self.h = width, height
        self.img = Image.new("RGB", (width, height), "white")
        self.d = ImageDraw.Draw(self.img)
        self.cell = cell
        self.origin = origin
        self._icon_cache: dict[tuple[str, int], Image.Image] = {}
        self.d.text((32, 24), title, font=F_TITLE, fill=INK)
        if subtitle:
            self.d.text((32, 56), subtitle, font=F_SUB, fill=MUTED)

    # grid -> pixel helper
    def gp(self, col: float, row: float) -> tuple[float, float]:
        return (self.origin[0] + col * self.cell[0], self.origin[1] + row * self.cell[1])

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

    def _text_block(self, xy, lines, font, fill, anchor="mm", spacing=3, bg=None):
        """Draw multiline text. anchor: 'mm' center x+y | 'ma' center x, top y | 'lt' left-top.

        Returns (top, bottom) y coordinates of the drawn block."""
        widths = [self.d.textlength(t, font=font) for t in lines]
        lh = font.size + spacing
        total_h = lh * len(lines) - spacing
        w = max(widths) if widths else 0
        x, y = xy
        top = y - total_h / 2 if anchor == "mm" else y
        if bg is not None:
            pad = 3
            if anchor in ("mm", "ma"):
                self.d.rectangle(
                    [x - w / 2 - pad, top - pad, x + w / 2 + pad, top + total_h + pad],
                    fill=bg,
                )
            else:
                self.d.rectangle([x - pad, top - pad, x + w + pad, top + total_h + pad], fill=bg)
        for i, t in enumerate(lines):
            ly = top + i * lh
            if anchor in ("mm", "ma"):
                self.d.text((x, ly), t, font=font, fill=fill, anchor="ma")
            else:
                self.d.text((x, ly), t, font=font, fill=fill)
        return top, top + total_h

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
        """kind: 'azure' | 'local' | 'external' (dashed) | 'sub' (nested, lighter)."""
        border, fill, dashed = {
            "azure": (AZURE_BORDER, AZURE_FILL, False),
            "local": (LOCAL_BORDER, LOCAL_FILL, False),
            "external": (EXT_BORDER, EXT_FILL, True),
            "sub": (SUB_BORDER, SUB_FILL, False),
        }[kind]
        if fill:
            self.d.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=fill)
        if dashed:
            self._dashed_rrect((x0, y0, x1, y1), 10, border, 2)
        else:
            self.d.rounded_rectangle([x0, y0, x1, y1], radius=10, outline=border, width=2)
        self.d.text((x0 + 12, y0 + 8), label, font=F_CLUSTER, fill=INK)
        if sublabel:
            lw = self.d.textlength(label, font=F_CLUSTER)
            self.d.text((x0 + 12 + lw + 10, y0 + 10), sublabel, font=F_EDGE, fill=MUTED)
        return Shape(x0, y0, x1, y1)

    # -- nodes ---------------------------------------------------------------

    def _icon(self, path: str, size: int) -> Image.Image:
        key = (path, size)
        if key not in self._icon_cache:
            im = Image.open(path).convert("RGBA")
            im.thumbnail((size, size), Image.LANCZOS)
            self._icon_cache[key] = im
        return self._icon_cache[key]

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
    ) -> Shape:
        """Icon centered at (cx, cy) with up to 2 label lines below.

        `note` adds one extra small line (use for auth / billing remarks)."""
        im = self._icon(icon, icon_size)
        iw, ih = im.size
        self.img.paste(im, (int(cx - iw / 2), int(cy - ih / 2)), im)
        lines = label.split("\n")[:2]
        _, bottom = self._text_block(
            (cx, cy + ih / 2 + 6), lines, F_LABEL, label_color, anchor="ma"
        )
        if note:
            self.d.text((cx, bottom + 4), note, font=F_EDGE, fill=note_color, anchor="ma")
            bottom += 4 + F_EDGE.size
        return Shape(cx - iw / 2, cy - ih / 2, cx + iw / 2, bottom)

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
    ) -> Shape:
        """Small labelled box (workflow stage etc.). Label may be multiline."""
        x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        self.d.rounded_rectangle([x0, y0, x1, y1], radius=7, fill=fill, outline=border, width=2)
        self._text_block((cx, cy), label.split("\n"), font, text_color, anchor="mm")
        return Shape(x0, y0, x1, y1)

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
        label_dy: float = -10,
        label_dx: float = 0,
        width: int = 2,
        arrow: bool = True,
        via: list[tuple[float, float]] | None = None,
    ):
        """Arrow a -> b. a/b: Shape or (x, y).

        style: 'solid' (data) | 'dashed' (telemetry).
        route: 'straight' | 'hv' (horizontal then vertical) | 'vh'.
        via: explicit waypoint list (overrides route).
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
            ang = math.atan2(e[1] - s[1], e[0] - s[0])
            self._arrow_head(e, ang, color)

        if label:
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
            self._text_block(
                (lx + label_dx, ly + label_dy),
                label.split("\n"),
                F_EDGE,
                label_color or color,
                anchor="mm",
                bg=(255, 255, 255),
            )

    # -- legend + note band --------------------------------------------------

    def footer(
        self,
        notes: list[str],
        auth: list[str] | None = None,
        config_note: str | None = None,
    ):
        """Standard bottom band: legend row + config note + notes + auth summary.

        notes lines starting with '$' are drawn orange (billing), '@' blue (auth).
        config_note overrides the default lab-config caption (used by the
        docs/survey diagrams, which are not lab configurations)."""
        band_lines = len(notes) + (len(auth) if auth else 0)
        band_h = 46 + band_lines * 19
        y0 = self.h - band_h
        self.d.rectangle([0, y0, self.w, self.h], fill=(245, 245, 245))
        self.d.line([0, y0, self.w, y0], fill=(210, 210, 210), width=1)

        # legend row
        lx, ly = 32, y0 + 14
        self.d.line([lx, ly + 6, lx + 34, ly + 6], fill=EDGE, width=2)
        self._arrow_head((lx + 34, ly + 6), 0, EDGE, 7)
        self.d.text((lx + 42, ly), "data / control", font=F_EDGE, fill=INK)
        lx += 150
        self._dashed_line((lx, ly + 6), (lx + 34, ly + 6), TELEM, 2)
        self._arrow_head((lx + 34, ly + 6), 0, TELEM, 7)
        self.d.text((lx + 42, ly), "telemetry (OTel)", font=F_EDGE, fill=INK)
        lx += 165
        self.d.text((lx, ly), "auth", font=F_EDGE, fill=BLUE)
        lx += 45
        self.d.text((lx, ly), "billing note", font=F_EDGE, fill=ORANGE)
        lx += 105
        self.d.text(
            (lx, ly),
            config_note
            or "Lab config: public endpoints, no VNet (closed-network variant: docs/survey/architecture/07)",
            font=F_EDGE,
            fill=MUTED,
        )

        ty = y0 + 38
        for line in notes:
            color = INK
            if line.startswith("$"):
                color, line = ORANGE, line[1:]
            elif line.startswith("@"):
                color, line = BLUE, line[1:]
            self.d.text((32, ty), line, font=F_NOTE, fill=color)
            ty += 19
        if auth:
            for line in auth:
                self.d.text((32, ty), line, font=F_NOTE, fill=BLUE)
                ty += 19

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.img.save(path)
        print(f"wrote {path} ({self.w}x{self.h})")


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
) -> dict[str, Shape]:
    """Shared-infra backdrop used by every port diagram: Azure subscription
    cluster > Foundry account (project + gpt-5.4-mini) + App Insights +
    Log Analytics. Returns shapes: azure, foundry, project, model, appi, logw."""
    azc = d.cluster(x0, y0, x1, y1, f"Azure subscription — {rg} (Japan East)", kind="azure")
    fc = d.cluster(
        x0 + 30, y0 + 50, x1 - 30, y0 + 50 + foundry_h,
        f"Foundry: aif-{base}", kind="sub",
        sublabel="shared infra (AIServices S0)",
    )
    mx = (x0 + x1) / 2
    ny = y0 + 50 + foundry_h * 0.42
    model = d.node(mx - 145, ny, icon("model"), "Model deployment\ngpt-5.4-mini", note=model_note)
    project = d.node(mx + 145, ny, icon("project"), "Project: maf-ports", note="system MI")
    appi = d.node(mx - 145, y1 - 108, icon("appinsights"), "App Insights\nappi-" + base)
    logw = d.node(mx + 145, y1 - 108, icon("loganalytics"), "Log Analytics\nlog-" + base)
    d.edge(appi, logw)
    return {"azure": azc, "foundry": fc, "project": project, "model": model, "appi": appi, "logw": logw}


NOTE_SHARED_ONLY = (
    "Infra: shared foundation only — infra/main.bicep holds existing references + outputs "
    "(no port-specific Azure resources)."
)
