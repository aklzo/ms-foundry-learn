"""E4: マルチモーダル生成(画像・動画、08章)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/e4-media-gen.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "E4: Image / video generation — queue-based load leveling is mandatory",
    width=1400,
    height=860,
    subtitle="Rate limits rule the design: images 6-36 RPM (Data Zone = 1/3), Sora 2 at "
    "2 job RPM + 2 concurrent + 24h job expiry. No official AAC pattern exists.",
)

api = d.node(140, 260, az("appservices/app-services.png"), "API",
             note="return job ID immediately")

azc = d.cluster(290, 110, 1360, 700, "Azure subscription", kind="azure")
queue = d.node(420, 280, az("storage/queues-storage.png"), "Queue\n(load leveling)")
worker = d.node(630, 280, icon("containerapp"), "Worker\n(rate-limited)",
                note="429 -> exponential backoff")
img = d.node(870, 200, icon("model"), "Images: sync API\n(gpt-image-2 GA / FLUX.2)",
             note="RPM only, no TPM; Data Zone = 1/3 of Global", note_color=ORANGE)
vid = d.node(870, 420, icon("model"), "Video: Sora 2 jobs\n(preview)",
             note="2 RPM / 2 concurrent / job expires in 24h", note_color=ORANGE)
blob = d.node(1130, 300, az("storage/blob-storage.png"), "Blob\n(evacuate <= 24h)",
              note="no BYO-storage output documented")
safety = d.box(1130, 500, 230, 48, "Content Safety +\nhuman review")
pub = d.box(1130, 610, 230, 44, "promote to\npublic storage")

d.edge(api, queue)
d.edge(queue, worker)
d.edge(worker, img, label="generate (sync)", label_t=0.35, label_dy=-24)
d.edge(worker, vid, label="create job -> poll\n(state in Cosmos DB)", label_t=0.5, label_dy=26)
d.edge(img, blob, route="hv")
d.edge(vid, blob, route="hv")
d.edge(blob, safety)
d.edge(safety, pub)

d.footer(
    notes=[
        "Provenance: images get C2PA Content Credentials automatically (doc is classic-portal "
        "only; gpt-image-2 not explicitly listed) - video has NO documented provenance -> DIY C2PA.",
        "Sora 2 RAI blocks: IP & photorealistic content, real people, copyrighted characters/music, "
        "faces in input images -> kills many commercial use cases; check at planning stage.",
        "Data-residency vs throughput collide head-on: Data Zone image RPM is 1/3 of Global. "
        "Minors' photorealistic images blocked by default (unlock = limited access).",
    ],
    config_note="Source: docs/survey/architecture/08 E4",
)

d.save(str(_here.parent.parent / "images" / "e4-media-gen.png"))
