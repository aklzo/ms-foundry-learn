"""Architecture diagram for github-mcp (Port 6).

Regenerate:  uv run --with diagrams,pillow python ports/github-mcp/docs/architecture.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, F_EDGE, MUTED, NOTE_SHARED_ONLY, TELEM, Diagram, icon, std_azure  # noqa: E402

d = Diagram(
    "github-mcp — remote MCP client (Port 6)",
    width=1400,
    height=790,
    subtitle="stdio/Docker MCP replaced by GitHub's official remote MCP server (GA) — connection runs "
    "client-side, zero port-specific Azure resources",
)

local = d.cluster(40, 100, 720, 470, "Local machine (uv + MAF)", kind="local")
ext = d.cluster(40, 510, 700, 665, "GitHub (outside Azure)", kind="external")

cli = d.node(110, 210, icon("cli"), "CLI\ngithub-mcp-maf")
agent = d.box(300, 200, 160, 56, "github_agent\n(MAF Agent)")
tool = d.box(490, 340, 230, 60, "MCPStreamableHTTPTool\nhttpx client (static headers)")
gh = d.node(200, 580, icon("github"), "GitHub remote MCP server\napi.githubcopilot.com/mcp (GA)")
d.d.text((320, 590), "headers: Authorization: Bearer <PAT>", font=F_EDGE, fill=MUTED)
d.d.text((320, 607), "X-MCP-Toolsets: repos,issues,pull_requests", font=F_EDGE, fill=MUTED)
d.d.text((320, 624), "X-MCP-Readonly: true (default on)", font=F_EDGE, fill=MUTED)

shared = std_azure(d, y1=660)

d.edge(cli, agent, label="query (+ --repo)", label_dy=-12)
d.edge(agent, tool, label="auto-connect\non run", label_t=0.55, label_dy=0, label_dx=52)
d.edge(tool.port("bottom", 0.3), gh.port("right", 0.3),
       label="streamable HTTP (initialize / tools/list / tools/call)\nPAT (Authorization: Bearer) on every request",
       label_color=BLUE, label_t=0.5, label_dy=-4, label_dx=110)
d.edge(agent, shared["model"], label="chat + tool loop / api-key", label_color=BLUE,
       label_t=0.45, label_dy=-14)
d.edge(local.port("right", 0.85), shared["appi"], style="dashed", color=TELEM,
       label="OTel traces (invoke_agent\n+ MCP tools/call spans)", label_t=0.5, label_dy=-6)

d.footer(
    notes=[
        NOTE_SHARED_ONLY + "  MCP connection is client-side: no Docker, no Azure resource.",
        "$No extra Azure billing (model tokens only). GitHub side: PAT rate limits, no cost. "
        "Write tools trimmed server-side via X-MCP-Readonly.",
    ],
    auth=[
        "Auth: model = api-key (lab .env) / GitHub MCP = PAT Bearer via http_client headers "
        "(header_provider only fires on tools/call — connect would 401) / traces = App Insights conn string",
    ],
)

d.save(str(_here.parent / "architecture.png"))
