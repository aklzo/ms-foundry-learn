"""E1: 音声エージェント / コンタクトセンター(08章)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/e1-voice.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, F_CLUSTER, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "E1: 音声エージェント / コンタクトセンター — Voice Live + ACS(SIP は直接受けない)",
    width=1560,
    height=820,
    subtitle="Voice Live = STT + LLM + TTS + アバターを 1 つの API で提供するマネージド speech-to-speech。"
    "電話は ACS(またはサードパーティ音声コネクタ)経由で受ける",
)

# --- 電話網(Azure 外・左) ------------------------------------------------------------
d.cluster(40, 110, 230, 600, "電話網", kind="external")
caller = d.node(135, 250, res("onprem/client/user.png"), "発信者", note="PSTN / SIP / PBX")

# --- Azure ------------------------------------------------------------------------
d.cluster(260, 100, 1520, 620, "Azure サブスクリプション", kind="azure")
acs = d.node(385, 250, az("other/azure-communication-services.png"), "ACS Call Automation",
             note="ACS 番号 / Direct Routing")
mid = d.node(595, 250, az("appservices/app-services.png"), "自社ミドル層", note="クライアント直結はしない")
d.box(490, 415, 390, 52, "Japan East: gpt-realtime 系・HD voice・アバターなし\n→ gpt-4.1 / gpt-5 系 + Azure STT / TTS で組む",
      fill=(255, 241, 240), border=(207, 34, 46), text_color=(180, 35, 45))

VL = "Voice Live API"
d.cluster(710, 140, 1150, 460, VL, kind="focus")
_p = d.pill(722 + d.d.textlength(VL, font=F_CLUSTER) + 8, 157, "GA")
d.text(_p.x1 + 8, 150, "Foundry リソース推奨")
sess = d.node(800, 250, icon("speech"), "セッション", note="WebSocket")
stt = d.box(1040, 185, 176, 38, "STT(Azure / MAI / Whisper)")
llm = d.box(1040, 250, 176, 38, "LLM(realtime / GPT 系)")
tts = d.box(1040, 315, 176, 38, "TTS(600+ 音声)")
tools = d.box(930, 415, 330, 36, "function calling / MCP / VoiceRAG")

d.cluster(1180, 140, 1500, 600, "Foundry プロジェクト", kind="sub")
agent = d.node(1340, 250, icon("foundry"), "Foundry エージェント", note="prompt / hosted")
byom = d.node(1340, 405, icon("model"), "BYOM(自前デプロイ)", note="独自フィルタ・PTU・国内処理")
vagent = d.box(1340, 530, 270, 52, "voice-based agent(kind: voice)\nミドル層不要・Voice Live 上で実行",
               status="Preview")

# --- 処理の流れ(下段) ----------------------------------------------------------------
d.steps_panel(40, 650, 1520, [
    "着信を ACS が受ける(ACS 番号 / Direct Routing)",
    "双方向の音声ストリームをミドル層へ(WebSocket)",
    "ミドル層から Voice Live へ(WebSocket + Entra ID)",
    "STT → LLM → TTS で応答を生成(ツール・エージェント連携)",
    "生成音声をセッション → ミドル層 → ACS で通話へ戻す",
], columns=3)

# --- edges ------------------------------------------------------------------------
d.edge(caller, acs, step=1, label_t=0.5)
d.edge(acs, mid, both=True, step=2, label_t=0.5)
d.edge(mid, sess, both=True, step=3, label_t=0.5)
d.edge(sess, stt, step=4, label_t=0.5)
d.edge(stt, llm)
d.edge(llm, tts)
d.edge(tts, sess, step=5, label_t=0.5)
d.edge(llm, agent, color=BLUE, label="エージェント連携\n(Entra 必須)", label_color=BLUE, label_t=0.64,
       label_dy=-22)
d.edge(llm.port("right", 0.8), byom, label="BYOM", label_t=0.62, label_dx=-28, label_dy=0)
d.edge((135, 322), vagent, via=[(135, 530)], label="電話番号の紐づけ(Teams Phone / Twilio)",
       label_t=0.42, label_dy=-14)

d.notes(
    [
        ("制約", "AOAI Realtime の SIP 直収は swedencentral / eastus2 のみ → 国内 PSTN は ACS Direct Routing か Twilio / Genesys 等の音声コネクタ経由"),
        ("課金", "サイジングはクォータ起点: 最大セッション 60 分・NCPM 100・TPM ≤ 120,000(ページ内で不整合)→ コンタクトセンター規模は増枠申請が必須"),
        ("運用", "429 はオートスケール追随中にも出る → 指数バックオフ + 段階投入(20 接続から 90〜120 秒ごとに +20)"),
        ("注意", "Voice Live のフィルタは変更・無効化できず、音声モデルはフィルタ対象外 → 独自ポリシーは BYOM(Foundry リソース必須)"),
        ("認証", "Entra ID 推奨(エージェント連携は Entra 必須)。WebRTC はプレビュー → 本番は WebSocket"),
    ],
    source="出典: docs/survey/architecture/08 E1",
)

d.save(
    str(_here.parent.parent / "images" / "e1-voice.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "e1-voice.png"),
)
