"""claim-voice-live(Port 12)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate(labs/maf-ports で):
    uv run --with diagrams,pillow python ports/claim-voice-live/docs/architecture.py
"""

import sys
from itertools import pairwise
from pathlib import Path

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, F_EDGE, MUTED, TELEM, Diagram, icon, res

d = Diagram(
    "claim-voice-live — Voice Live で音声 FNOL 受付(Port 12)",
    width=1400,
    height=900,
    subtitle="3 層: 音声非依存の FNOL コア(MAF ワークフロー)/ テキスト対話層 / Voice Live 層。"
    "コアは関数ツール process_claim_turn として Voice Live に接続する",
)

# --- 請求者(Azure 外・左) -----------------------------------------------------------------
d.cluster(40, 110, 215, 625, "請求者", kind="external", sublabel="Azure 外")
user = d.node(127, 220, res("onprem/client/user.png"), "請求者", icon_size=56,
              note="テキストで入力")

# --- ローカル(uv + MAF): 3 層 -----------------------------------------------------------
d.cluster(240, 100, 880, 640, "ローカル(uv + MAF)", kind="local")
d.cluster(260, 140, 860, 270, "層 3: Voice Live 層", kind="sub", sublabel="scripts/voice_session.py")
voice = d.box(560, 220, 420, 48,
              "WebSocket クライアント(session.update・tools)\nテキストターン送信 / 音声チャンクは破棄")
core = d.cluster(260, 315, 860, 465, "層 1: FNOL コア(MAF ワークフロー・音声非依存)", kind="focus")
stage_labels = ["extract*", "validate", "classify*", "rules", "checklist", "gate", "packet"]
stages = [d.box(320 + 80 * i, 380, 70, 36, s, font=F_EDGE) for i, s in enumerate(stage_labels)]
for a, b in pairwise(stages):
    d.edge(a, b, width=1)
d.text(560, 420, "* = LLM 段(構造化出力)/ 他 5 段は決定論(policies.py)", fill=MUTED, anchor="ma")
d.cluster(260, 495, 860, 620, "層 2: テキスト対話層", kind="sub", sublabel="CLI claim-voice-live-maf")
cli = d.box(560, 565, 420, 44, "ターン蓄積 → コア実行 → 決定論の次質問\n(ライブスモークの主経路)")

# --- Azure ----------------------------------------------------------------------------
d.cluster(905, 100, 1360, 670, "Azure サブスクリプション — rg-maf-ports(Japan East)", kind="azure")
d.cluster(925, 145, 1340, 490, "Foundry: aif-mafportsw2", kind="sub", sublabel="共有基盤(AIServices S0)")
vl = d.node(1130, 220, icon("speech"), "Voice Live API\nマネージド gpt-4.1-mini", status="GA",
            note="Standard 価格帯・デプロイ不要")
model = d.node(1130, 390, icon("model"), "モデルデプロイ\ngpt-5.4-mini", status="GA",
               note="コアの LLM 2 段")
appi = d.node(1030, 580, icon("appinsights"), "App Insights\nappi-mafportsw2")
logw = d.node(1250, 580, icon("loganalytics"), "Log Analytics\nlog-mafportsw2")
d.edge(appi, logw)

# --- 処理の流れ(下段) -------------------------------------------------------------------
d.steps_panel(40, 700, 1360, [
    "請求者の発話をテキストターンで入力(音声入力は拡張点)",
    "WSS(api-version=2026-04-10)で Voice Live へ送信 → モデルが process_claim_turn を呼ぶ",
    "毎ターン全文で FNOL コア 7 段を実行し、ルートと次質問を返す",
    "LLM 2 段(extract / classify)がモデルを構造化出力で呼ぶ",
], columns=2)

# --- edges ----------------------------------------------------------------------------
d.edge(user, voice, both=True, step=1, label_t=0.77)
d.edge(voice, vl, both=True, step=2, label="api-key", label_color=BLUE, label_t=0.73,
       label_pos="above")
d.edge(voice, core.port("top", 0.5), both=True, step=3, label="全文を渡す", label_t=0.68)
d.edge(core.port("right", (390 - 315) / (465 - 315)), model, step=4, label="api-key",
       label_color=BLUE, label_t=0.6, label_pos="above")
d.edge(user, cli, via=[(127, 565)], label="テキスト(CLI)", label_t=0.4, label_dx=0, label_dy=0)
d.edge(cli.port("top", (700 - 350) / 420), core.port("bottom", (700 - 260) / 600), label="同じコア",
       label_t=0.3, label_dx=38, label_dy=0)
d.edge((880, 580), appi, style="dashed", color=TELEM, label="OTel(任意)", label_t=0.6,
       label_dy=-14)

d.notes(
    [
        ("課金", (
            "Voice Live はセッション中のトークン + 音声で課金(gpt-4.1-mini = Standard 価格帯。"
            "2026-09-29 に Basic から改称)。スモークは短文 1〜2 往復に留める"
        )),
        ("制約", (
            "Japan East では gpt-realtime 系・azure-realtime が Voice Live 非提供、gpt-5.4-mini は BYOM"
            " → 既定はテキストモデル gpt-4.1-mini + Azure STT(azure-speech)/ TTS"
        )),
        ("運用", (
            "追加 ARM リソースなし — Voice Live は共有 Foundry リソースのデータプレーン。"
            "モデルはサービス側のマネージド提供(デプロイ・容量計画・Bicep 不要)"
        )),
        ("認証", (
            "Voice Live WSS = api-key(Entra なら Cognitive Services User + Foundry User)/ "
            "コアの LLM = api-key(OpenAI v1)/ トレース = App Insights 接続文字列"
        )),
        ("注意", (
            "ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)。"
            "マイク/スピーカーなし — ライブ検証は接続 + テキスト往復 + ツールループまで"
        )),
    ],
    source="出典: labs/maf-ports/ports/claim-voice-live/README.md",
)

d.save(str(_here.parent / "architecture.png"))
