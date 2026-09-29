"""C2: マルチテナント SaaS(06章)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

C1 / C3 は本図の部分集合(単一テナント / APIM 按分)のため個別図は作らない。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/c2-multitenant-saas.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "C2: マルチテナント SaaS — 既定は共有、専用は理由があるときだけ",
    width=1560,
    height=800,
    subtitle="公式の既定は共有モデルデプロイ。専用デプロイは TPM 割当・課金按分 / フィルタ方針 / モデルの"
    "ライフサイクル / ファインチューニング / データ所在のいずれかが要るときだけ作る",
)

# --- テナント(Azure 外・左) ----------------------------------------------------------
d.cluster(40, 110, 250, 470, "テナント", kind="external")
ta = d.node(145, 230, res("onprem/client/users.png"), "テナント A", note="小口・多数")
tb = d.node(145, 380, res("onprem/client/users.png"), "テナント B", note="大口")
d.box(145, 555, 196, 92, "分離の単位(3 モデル)\n① 共有 + 論理分離\n② テナント別デプロイ\n③ テナント別リソース",
      fill=(255, 255, 255), border=(190, 198, 208), text_color=(70, 76, 82))

# --- Azure(SaaS 提供者) ------------------------------------------------------------
d.cluster(280, 100, 1520, 640, "Azure サブスクリプション(SaaS 提供者)", kind="azure")

d.cluster(300, 140, 610, 620, "SaaS アプリ", kind="focus", sublabel="テナント文脈の強制点")
app = d.node(455, 230, az("appservices/app-services.png"), "Web / API",
             note="テナント ID はトークンから", note_color=BLUE)
api = d.box(455, 490, 230, 56, "データ API 層\n(ゲートキーパー)")

apim = d.node(760, 230, az("integration/api-management.png"), "APIM(AI ゲートウェイ)",
              note="テナント別 TPM・トークン計測", note_color=ORANGE)

d.cluster(900, 140, 1500, 330, "Foundry", kind="sub")
shared = d.node(1060, 230, icon("model"), "共有デプロイ", note="公式の既定(Standard)")
dedic = d.node(1340, 230, icon("model"), "専用デプロイ", note="大口テナント(PTU)")

d.cluster(700, 380, 1500, 620, "テナントデータ", kind="sub", sublabel="テナント専用ストア or 共有 + テナントフィルタ")
search = d.node(850, 490, icon("search"), "AI Search", note="インデックス / テナント")
cosmos = d.node(1100, 490, az("databases/azure-cosmos-db.png"), "Cosmos DB",
                note="会話・response ID(テナントキー)")
blob = d.node(1350, 490, az("storage/blob-storage.png"), "Blob", note="コンテナ / テナント")

# --- 処理の流れ(下段) ------------------------------------------------------------------
d.steps_panel(40, 670, 1520, [
    "トークンからテナント ID を確定(LLM に伝搬させない)",
    "データ API 層がそのテナントのデータだけを取得",
    "APIM がテナント別に TPM 制限・トークン計測",
    "既定は共有デプロイ、大口は専用デプロイへ",
], columns=2)

# --- edges --------------------------------------------------------------------------
d.edge(ta, app, both=True, step=1, label_t=0.36)
d.edge(tb, (423, 246))
d.edge(app, api, label="直接クエリ禁止", label_t=0.55, label_dx=52, label_dy=0)
d.edge(api, search, step=2, label_t=0.45)
d.edge(app, apim, step=3, label_t=0.62)
d.edge(apim, shared, step=4, label_t=0.66)
d.edge(dedic, shared, label="スピルオーバー", label_t=0.5, label_dy=-14)

d.notes(
    [
        ("制約", "共有リソースはデプロイ単位のセキュリティ分離を持たない → テナントとデプロイの対応はアプリが強制。FT 済みモデルのリソースは共有しない"),
        ("注意", "Responses API はテナント分離が難しい(公式): response ID はテナントキー付きで自前保存、組込みツール(Code Interpreter / MCP)はテナント別構成に"),
        ("課金", "テナント別按分はアプリ側の自前実装が公式回答。APIM の llm-emit-token-metric にテナント ID をカスタム次元で追加"),
        ("制約", "hosted agent の同時セッションは sub × リージョン既定 2,000(Japan East)。閉域はサブネット IP と 1:1 → 大規模 SaaS は分割を検討"),
        ("推奨", "B2C のように小規模テナントが多いならストア共有 + テナントフィルタ(テナント専用ストアは使わない)"),
    ],
    source="出典: docs/survey/architecture/06 C2",
)

d.save(
    str(_here.parent.parent / "images" / "c2-multitenant-saas.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "c2-multitenant-saas.png"),
)
