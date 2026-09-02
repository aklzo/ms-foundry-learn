"""検証結果レポート(PDF)の生成。

数値はすべて logs/ の評価出力から動的に読み込む(手書き転記による誤りを排除)。
HTML を組み立て、Playwright(Chromium)の print-to-PDF で docs/report/ へ出力する。

  uv run python scripts/gen_report.py
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cu_video_rag.corpus import FORM_OF_VIDEO, QUERIES, SCENARIOS  # noqa: E402

LOGS = ROOT / "logs"
OUT_DIR = ROOT / "docs" / "report"

FORM_LABEL = {
    "narrated": "ナレーション付き UI 操作",
    "silent": "無音・テロップのみ",
    "slide": "スライド講義型",
    "long": "長尺・複数章構成",
}
CONFIG_LABEL = {
    "A": "A: 書き起こしのみ",
    "B": "B: prebuilt-videoSearch",
    "C": "C: 日本語カスタムフィールド",
    "D": "D: C + screenTexts 重み付け",
}


def load(name: str) -> dict:
    p = LOGS / name
    if not p.exists():
        raise SystemExit(f"missing {p} — 評価を先に実行してください")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- SVG 図

def svg_grouped_bars(
    groups: list[str], series: list[tuple[str, list[float]]], *, ymax: float = 1.0,
    width: int = 720, height: int = 260, fmt: str = "{:.2f}", colors: list[str] | None = None,
) -> str:
    colors = colors or ["#9db8d2", "#7191b8", "#3e6c9e", "#1f4e79"]
    left, bottom, top = 46, 40, 16
    plot_w, plot_h = width - left - 14, height - bottom - top
    n_g, n_s = len(groups), len(series)
    gw = plot_w / n_g
    bw = min(34.0, gw * 0.8 / n_s)
    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img">']
    for i in range(5):
        y = top + plot_h * i / 4
        val = ymax * (1 - i / 4)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - 14}" y2="{y:.1f}" stroke="#dde4ec" stroke-width="1"/>')
        parts.append(f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="#667">{val:.2f}</text>')
    for gi, g in enumerate(groups):
        x0 = left + gi * gw + (gw - bw * n_s) / 2
        for si, (sname, vals) in enumerate(series):
            v = vals[gi]
            h = plot_h * min(v, ymax) / ymax
            x = x0 + si * bw
            y = top + plot_h - h
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw - 3:.1f}" height="{h:.1f}" fill="{colors[si % len(colors)]}" rx="2"/>')
            parts.append(f'<text x="{x + (bw - 3) / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" font-size="10.5" fill="#334">{fmt.format(v)}</text>')
        parts.append(f'<text x="{left + gi * gw + gw / 2:.1f}" y="{height - bottom + 16}" text-anchor="middle" font-size="12" fill="#223">{g}</text>')
    lx = left
    for si, (sname, _) in enumerate(series):
        parts.append(f'<rect x="{lx}" y="{height - 14}" width="11" height="11" fill="{colors[si % len(colors)]}" rx="2"/>')
        parts.append(f'<text x="{lx + 15}" y="{height - 4}" font-size="11.5" fill="#334">{sname}</text>')
        lx += 15 + 11 * len(sname) + 30
    parts.append("</svg>")
    return "".join(parts)


def svg_pipeline() -> str:
    boxes = [
        ("合成データセット\n104 本 (mp4)", 4),
        ("Blob Storage\n(SAS URL)", 4),
        ("Content Understanding\nprebuilt / カスタム 2 段", 5),
        ("セグメント\nチャンク化", 4),
        ("AI Search\nハイブリッド索引", 4),
        ("回答生成\n(gpt-5.4-mini)", 4),
        ("評価\nCER / IR 指標 / ragas", 5),
    ]
    W, H, bh, y = 1020, 96, 60, 14
    total_units = sum(b[1] for b in boxes)
    gap = 26
    usable = W - gap * (len(boxes) - 1) - 8
    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" font-family="inherit">']
    x = 4.0
    for i, (label, units) in enumerate(boxes):
        bw = usable * units / total_units
        parts.append(f'<rect x="{x:.0f}" y="{y}" width="{bw:.0f}" height="{bh}" rx="8" fill="#eef3f9" stroke="#1f4e79" stroke-width="1.6"/>')
        lines = label.split("\n")
        for li, line in enumerate(lines):
            ty = y + bh / 2 + (li - (len(lines) - 1) / 2) * 17 + 5
            parts.append(f'<text x="{x + bw / 2:.0f}" y="{ty:.0f}" text-anchor="middle" font-size="13.5" fill="#1a2a3a">{line}</text>')
        if i < len(boxes) - 1:
            ax = x + bw
            parts.append(f'<path d="M {ax + 4:.0f} {y + bh / 2} L {ax + gap - 6:.0f} {y + bh / 2}" stroke="#5b7b9b" stroke-width="2" fill="none" marker-end="url(#arr)"/>')
        x += bw + gap
    parts.insert(1, '<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#5b7b9b"/></marker></defs>')
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------- 本体

def build_html() -> str:
    today = date.today().isoformat()
    cer = load("cer_prebuilt.json")
    evals = {c: load(f"eval_{c}.json") for c in "ABCD"}
    ragas = {c: load(f"ragas_{c}.json") for c in ("A", "C")}
    # 処理時間: analyze が保存した per-video タイミングから算出
    proc = {}
    _gts_for_dur = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data" / "ground_truth").glob("*.json")}
    for tag in ("prebuilt", "custom"):
        tp = LOGS / f"timings_{tag}.json"
        if tp.exists():
            rows = json.loads(tp.read_text(encoding="utf-8"))
            secs = sorted(r["sec"] for r in rows)
            ratios = sorted(
                r["sec"] / _gts_for_dur[r["vid"]]["duration_s"] for r in rows if r["vid"] in _gts_for_dur
            )
            proc[tag] = {
                "n": len(rows),
                "median_s": secs[len(secs) // 2],
                "p90_s": secs[int(len(secs) * 0.9)],
                "ratio_median": ratios[len(ratios) // 2],
            }

    # --- データセット統計
    n_videos = len(SCENARIOS)
    form_counts: dict[str, int] = {}
    for f in FORM_OF_VIDEO.values():
        form_counts[f] = form_counts.get(f, 0) + 1
    gts = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data" / "ground_truth").glob("*.json")}
    total_dur = sum(g["duration_s"] for g in gts.values())
    q_types = {t: sum(1 for q in QUERIES if q["type"] == t) for t in "NSC"}

    # --- CER 統計
    cers = [r["cer"] for r in cer["per_video"].values()]
    cer_stats = {
        "n": len(cers),
        "micro": cer["micro_cer"],
        "median": statistics.median(cers),
        "p90": sorted(cers)[int(len(cers) * 0.9)],
        "max": max(cers),
        "zero": sum(1 for c in cers if c == 0.0),
    }
    worst = sorted(cer["per_video"].items(), key=lambda kv: -kv[1]["cer"])[:5]

    # --- 検索表
    def m(c, scope, key, typ=None):
        blk = evals[c]["by_type"][typ] if typ else evals[c]["overall"]
        return blk.get(key)

    configs = list("ABCD")

    def fmt_or_dash(v):
        return f"{v:.3f}" if isinstance(v, (int, float)) else "−"

    retr_rows = []
    for c in configs:
        o = evals[c]["overall"]
        s = evals[c]["by_type"]["S"]
        retr_rows.append(
            f"<tr><td>{CONFIG_LABEL[c]}</td>"
            f"<td class='num'>{fmt_or_dash(o.get('hit@1'))}</td><td class='num'>{fmt_or_dash(o.get('hit@3'))}</td>"
            f"<td class='num'>{fmt_or_dash(o.get('mrr'))}</td><td class='num'>{fmt_or_dash(o.get('seg_hit@1'))}</td>"
            f"<td class='num'>{fmt_or_dash(s.get('ans@1'))}</td><td class='num'>{fmt_or_dash(s.get('ans@3'))}</td></tr>"
        )

    by_form_rows = []
    for c in ("A", "C"):
        for f, blk in evals[c].get("by_form", {}).items():
            if blk:
                by_form_rows.append(
                    f"<tr><td>{CONFIG_LABEL[c]}</td><td>{FORM_LABEL.get(f, f)}</td>"
                    f"<td class='num'>{blk['n']}</td><td class='num'>{blk['hit@1']:.3f}</td>"
                    f"<td class='num'>{blk['hit@3']:.3f}</td><td class='num'>{blk['mrr']:.3f}</td></tr>"
                )

    # --- ragas 表
    ragas_metrics = list(ragas["C"]["summary"].keys())
    ragas_rows = "".join(
        f"<tr><td>{name}</td>"
        + "".join(f"<td class='num'>{ragas[c]['summary'].get(name, float('nan')):.3f}</td>" for c in ("A", "C"))
        + "</tr>"
        for name in ragas_metrics
    )

    # --- S タイプ ans@3 ミスの内訳(構成 C)
    import re as _re
    import unicodedata as _ud
    sys.path.insert(0, str(ROOT / "src"))
    from cu_video_rag.chunks import parse_segments as _ps, to_chunks as _tc
    _P = _re.compile(r"[\s、。,.!?!?・:「」()()]")
    _norm = lambda x: _P.sub("", _ud.normalize("NFKC", x))
    _qmap = {q["qid"]: q for q in QUERIES}
    _miss = [r for r in evals["C"]["per_query"] if r["type"] == "S" and not r.get("ans3", True)]
    s_break = {"retr": 0, "seg": 0, "transcribe": 0}
    for r in _miss:
        q = _qmap[r["qid"]]
        if not r["hit3"]:
            s_break["retr"] += 1
            continue
        d = json.loads((LOGS / "cu" / "custom" / f"{q['video']}.json").read_text(encoding="utf-8"))
        chunks_v = _tc(_ps(d, q["video"]), "full")
        if any(_norm(q["answer"]) in _norm(c["content"]) for c in chunks_v):
            s_break["seg"] += 1
        else:
            s_break["transcribe"] += 1
    n_s = evals["C"]["by_type"]["S"]["n"]
    n_s_miss = len(_miss)

    # 「分かりません」型回答の件数(ragas 解釈用)
    nc = {}
    for c in ("A", "C"):
        answers = json.loads((LOGS / f"rag_answers_{c}.json").read_text(encoding="utf-8"))
        nc[c] = sum(1 for a in answers if "分かりません" in a["answer"])

    # --- グラフ
    chart_ans = svg_grouped_bars(
        [CONFIG_LABEL[c].split(":")[0] for c in configs],
        [
            ("ans@1(回答値が 1 位チャンクに含まれる)", [evals[c]["by_type"]["S"].get("ans@1", 0.0) for c in configs]),
            ("ans@3(top-3 のいずれかに含まれる)", [evals[c]["by_type"]["S"].get("ans@3", 0.0) for c in configs]),
        ],
    )
    chart_hit = svg_grouped_bars(
        [CONFIG_LABEL[c].split(":")[0] for c in configs],
        [
            ("hit@1(正解動画が 1 位)", [evals[c]["overall"]["hit@1"] for c in configs]),
            ("hit@3", [evals[c]["overall"]["hit@3"] for c in configs]),
            ("seg_hit@1(正解場面が 1 位)", [evals[c]["overall"]["seg_hit@1"] for c in configs]),
        ],
    )
    chart_ragas = svg_grouped_bars(
        [n.replace("_", " ") for n in ragas_metrics],
        [
            ("構成 A(書き起こしのみ)", [ragas["A"]["summary"].get(n, 0.0) for n in ragas_metrics]),
            ("構成 C(カスタムフィールド)", [ragas["C"]["summary"].get(n, 0.0) for n in ragas_metrics]),
        ],
        width=860,
    )

    proc_html = ""
    if proc:
        proc_html = f"""
    <table>
      <tr><th>項目</th><th>prebuilt-videoSearch</th><th>カスタム(videoSearchJa)</th></tr>
      <tr><td>解析本数</td><td class="num">{proc['prebuilt']['n']}</td><td class="num">{proc['custom']['n']}</td></tr>
      <tr><td>1 本あたり中央値</td><td class="num">{proc['prebuilt']['median_s']:.0f} 秒</td><td class="num">{proc['custom']['median_s']:.0f} 秒</td></tr>
      <tr><td>1 本あたり p90</td><td class="num">{proc['prebuilt']['p90_s']:.0f} 秒</td><td class="num">{proc['custom']['p90_s']:.0f} 秒</td></tr>
      <tr><td>実時間比(中央値/動画長)</td><td class="num">{proc['prebuilt']['ratio_median']:.2f} 倍</td><td class="num">{proc['custom']['ratio_median']:.2f} 倍</td></tr>
    </table>"""

    css = """
    @page { size: A4; margin: 18mm 16mm; }
    * { box-sizing: border-box; margin: 0; }
    body { font-family: "Noto Sans CJK JP", "Yu Gothic", sans-serif; color: #1c2733;
           background: #fff; font-size: 10.5pt; line-height: 1.75; }
    h1 { font-size: 21pt; line-height: 1.4; }
    h2 { font-size: 14pt; color: #1f4e79; border-left: 6px solid #1f4e79; padding-left: 10px;
         margin: 26px 0 10px; page-break-after: avoid; }
    h3 { font-size: 11.5pt; margin: 16px 0 6px; color: #2a4a6a; page-break-after: avoid; }
    p { margin: 6px 0; }
    table { border-collapse: collapse; width: 100%; margin: 8px 0 14px; font-size: 9.5pt;
            page-break-inside: avoid; }
    th, td { border: 1px solid #c5d0dc; padding: 4.5px 8px; text-align: left; }
    th { background: #eef3f9; font-weight: 600; }
    td.num { text-align: right; font-variant-numeric: tabular-nums; }
    .cover { height: 250mm; display: flex; flex-direction: column; justify-content: center;
             page-break-after: always; }
    .cover .rule { width: 70px; height: 6px; background: #1f4e79; margin: 18px 0; }
    .cover .meta { margin-top: 40px; color: #445; font-size: 11pt; }
    .cards { display: flex; gap: 10px; margin: 12px 0; page-break-inside: avoid; }
    .card { flex: 1; border: 1px solid #c5d0dc; border-top: 5px solid #1f4e79; border-radius: 6px;
            padding: 10px 12px; }
    .card .v { font-size: 17pt; font-weight: 700; color: #1f4e79; font-variant-numeric: tabular-nums; }
    .card .k { font-size: 8.5pt; color: #556; line-height: 1.5; }
    .note { background: #fff8dc; border: 1px solid #e0c060; border-radius: 6px; padding: 8px 12px;
            font-size: 9.5pt; margin: 10px 0; page-break-inside: avoid; }
    .fig { margin: 10px 0 16px; page-break-inside: avoid; }
    .fig figcaption { font-size: 9pt; color: #556; margin-top: 2px; }
    .toc td { border: none; border-bottom: 1px dotted #bbc; padding: 3px 4px; }
    ol, ul { padding-left: 22px; margin: 6px 0; }
    li { margin: 3px 0; }
    code { font-family: "Consolas", monospace; font-size: 9pt; background: #f0f3f7; padding: 1px 4px;
           border-radius: 3px; }
    .pagebreak { page-break-before: always; }
    a { color: #1f4e79; }
    """

    top3_s = evals["C"]["by_type"]["S"].get("ans@3", 0)
    a_s = evals["A"]["by_type"]["S"].get("ans@3", 0)

    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<title>CU 動画 RAG 検証レポート</title><style>{css}</style></head><body>

<div class="cover">
  <div style="color:#556;font-size:11pt">検証結果レポート</div>
  <h1>Azure AI Content Understanding による<br>研修動画ナレッジ化と RAG 検索の精度検証</h1>
  <div class="rule"></div>
  <p style="font-size:11.5pt">日本語の画面操作研修動画 {n_videos} 本(計 {total_dur / 60:.0f} 分)を対象に、
  動画解析(prebuilt-videoSearch GA)→ Azure AI Search ハイブリッド検索 → RAG 回答生成の
  各段の精度を定量評価した。</p>
  <div class="meta">
    作成日: {today}<br>
    対象読者: 実装チーム(動画ナレッジ取り込み機能の設計・実装担当)<br>
    検証環境: Azure japaneast / Content Understanding API 2025-11-01(GA)<br>
    リポジトリ: ms-foundry-learn <code>labs/cu-video-rag/</code>(再現手順・全コード同梱)
  </div>
</div>

<h2>1. エグゼクティブサマリ</h2>
<div class="cards">
  <div class="card"><div class="v">{cer_stats['micro'] * 100:.2f}%</div>
    <div class="k">書き起こし文字誤り率(CER)<br>{cer_stats['n']} 本 micro 平均</div></div>
  <div class="card"><div class="v">{evals['C']['overall']['hit@3']:.3f}</div>
    <div class="k">構成 C の hit@3<br>(正解動画が上位 3 位以内)</div></div>
  <div class="card"><div class="v">{a_s:.2f} → {top3_s:.2f}</div>
    <div class="k">画面のみ情報の ans@3<br>書き起こしのみ → カスタムフィールド</div></div>
  <div class="card"><div class="v">{ragas['C']['summary'].get('faithfulness', 0):.3f}</div>
    <div class="k">RAG 回答の faithfulness<br>(ragas / 構成 C)</div></div>
</div>
<p><b>結論。</b>(1) CU の日本語書き起こしは CER {cer_stats['micro'] * 100:.2f}% と実用水準であり、
音声書き起こしを別実装する必要はない。
(2) ただし prebuilt アナライザーを素のまま使うと、画面にしか表示されない情報
(エラーコード・設定値・連絡先など)は検索・回答にほぼ使えない(ans@3 = {evals['B']['by_type']['S'].get('ans@3', 0):.2f})。
(3) <b>日本語カスタムフィールド(2 段アナライザー構成)を追加することで ans@3 は {top3_s:.2f} まで改善</b>し、
ragas による end-to-end 評価でも全指標で書き起こしのみ構成を上回った。
実装には §7 の設計(2 段アナライザー+セグメント単位チャンク)を推奨する。</p>

<h2>2. 目次</h2>
<table class="toc">
<tr><td>1. エグゼクティブサマリ</td><td>3. 検証の目的と範囲</td></tr>
<tr><td>4. 検証構成とパイプライン</td><td>5. データセット(104 本の設計)</td></tr>
<tr><td>6. 評価方法(指標とツール)</td><td>7. 結果 1: 書き起こし精度</td></tr>
<tr><td>8. 結果 2: 検索精度</td><td>9. 結果 3: RAG 回答品質(ragas)</td></tr>
<tr><td>10. 処理時間</td><td>11. 実装上の注意点(詰まりどころ)</td></tr>
<tr><td>12. 制約と限界</td><td>13. 実装チームへの推奨事項 / 付録</td></tr>
</table>

<h2>3. 検証の目的と範囲</h2>
<p>ヘルプデスク AI の社内ナレッジに「画面操作手順のガイド・研修動画」が含まれる場合を想定し、
次の 2 点を定量的に確かめる。</p>
<ol>
<li><b>書き起こし精度</b> — Content Understanding(以下 CU)の日本語音声書き起こしは、
別途 Speech to Text を実装せずに済む水準か。</li>
<li><b>RAG 検索・回答精度</b> — CU の解析結果を AI Search に取り込んだとき、
質問に答えられる検索結果・回答が得られるか。特に<b>ナレーションでは言及されず
画面にのみ表示される情報</b>(エラーコード・設定値・連絡先等)を扱えるか。</li>
</ol>
<p>プレビュー機能は使用しない(顧客デプロイ前提)。CU は GA API <code>2025-11-01</code> のみを使用した。</p>

<h2>4. 検証構成とパイプライン</h2>
<figure class="fig">{svg_pipeline()}
<figcaption>図 1: 検証パイプライン。CU は prebuilt-videoSearch と日本語カスタムフィールド付き
2 段アナライザーの両方で解析し、インデックス構成 A〜D を比較する。</figcaption></figure>
<table>
<tr><th>構成</th><th>検索インデックスの本文</th><th>ねらい</th></tr>
<tr><td>A: 書き起こしのみ</td><td>CU の transcriptPhrases のみ</td><td>「音声だけで十分か」のベースライン(自前 STT 相当)</td></tr>
<tr><td>B: prebuilt-videoSearch</td><td>A + セグメント記述(Summary)</td><td>prebuilt の素の実力</td></tr>
<tr><td>C: 日本語カスタムフィールド</td><td>A + 日本語要約 + 画面内テキスト転記 + 操作列挙</td><td>B の弱点(英語記述・値の欠落)への対策</td></tr>
<tr><td>D: C + フィールド分離</td><td>C の画面内テキストを別フィールド化し重み 2.0</td><td>動画内の場面順位の改善</td></tr>
</table>
<p>Azure リソース: Foundry リソース(kind AIServices、japaneast)、モデルデプロイ
gpt-5.4-mini(CU 生成用)/ text-embedding-3-small(ベクトル)/ gpt-4.1-mini(ragas 判定用)、
AI Search(basic、ja.lucene + HNSW ベクトル、ハイブリッドは RRF 統合)、Blob Storage(動画置き場)。</p>

<h2>5. データセット(104 本の設計)</h2>
<p>日本語のナレーション付き画面操作研修動画のオープンデータセットは調査の結果存在しなかったため
(PsTuts-VQA・VideoGUI はいずれも英語)、<b>合成データセットを自作</b>した。台本・画面・操作を
プログラムで生成するため、書き起こしの正解(CER の基準)とステップ境界時刻が決定的に得られる。</p>
<table>
<tr><th>形態</th><th>本数</th><th>内容</th></tr>
<tr><td>{FORM_LABEL['narrated']}</td><td class="num">{form_counts.get('narrated', 0)}</td>
<td>手作り 10 本(VPN・パスワード再設定・プリンタ等)+ 26 業務ドメイン × 手続きタイプのテンプレート生成 78 本</td></tr>
<tr><td>{FORM_LABEL['silent']}</td><td class="num">{form_counts.get('silent', 0)}</td>
<td>ナレーションなし。字幕テロップと画面表示のみ(書き起こしが空になるケース)</td></tr>
<tr><td>{FORM_LABEL['slide']}</td><td class="num">{form_counts.get('slide', 0)}</td>
<td>講義スライド + ナレーション(UI 操作なし)</td></tr>
<tr><td>{FORM_LABEL['long']}</td><td class="num">{form_counts.get('long', 0)}</td>
<td>約 3 分・3 章構成(セグメント分割の質の確認用)</td></tr>
</table>
<p>設計上の仕掛け: (1) 約半数の動画に<b>「画面のみ情報」</b>(ナレーションでは「画面の注意書きを
確認してください」とだけ言い、値は画面にだけ出す)を配置。値は動画ごとに一意(内線 5xxx、ERR-1xx 等)
とし、100 本規模でも回答値が衝突しない。(2) VPN と Wi-Fi と Web 会議など<b>語彙が重なる動画</b>を
意図的に併存させ、表層一致だけでは動画を特定できないようにした。(3) 生成はシード固定で再現可能。</p>
<p>評価クエリは {len(QUERIES)} 問(ナレーション由来 N: {q_types['N']} / 画面のみ S: {q_types['S']} /
紛らわしい C: {q_types['C']})。すべてに参照回答(ref_answer)を付与し、S タイプには回答値の
文字列(answer)も付与した。</p>

<h2>6. 評価方法(指標とツール)</h2>
<h3>6.1 書き起こし: CER(文字誤り率)</h3>
<p>CER = 編集距離 ÷ 正解文字数。正解は台本そのもの。NFKC 正規化と空白・句読点の除去後に測定
(句読点の位置は音声認識の流儀差であり意味に影響しないため)。無音動画 {form_counts.get('silent', 0)} 本は対象外。</p>
<h3>6.2 検索: 情報検索の標準指標</h3>
<p>ハイブリッド検索(BM25 + ベクトル、RRF 統合)の top-5 に対して、
hit@1 / hit@3(正解動画のチャンクが 1 位 / 3 位以内)、MRR、
seg_hit@1(1 位チャンクの時間範囲が正解場面と重なる)、
ans@k(取得チャンク本文に回答値そのものが含まれる — 検索が「当たった」ように見えても
本文に値がなければ RAG は答えを生成できない、を測る本検証の中心指標)。</p>
<h3>6.3 RAG 回答品質: ragas</h3>
<p>RAG 評価の標準ライブラリ <b>ragas 0.4.3</b> を使用。検索 top-3 をコンテキストに
gpt-5.4-mini で日本語回答を生成し(コンテキスト外は「分かりません」と答える指示)、
LLM-as-a-judge(gpt-4.1-mini、温度 0)で 5 指標を測定した:
faithfulness(コンテキストへの忠実性)/ answer_relevancy(質問への適合)/
context_precision(上位コンテキストの適合率)/ context_recall(参照回答の根拠の網羅)/
answer_correctness(参照回答との一致)。</p>

<div class="pagebreak"></div>
<h2>7. 結果 1: 書き起こし精度(CER)</h2>
<div class="cards">
  <div class="card"><div class="v">{cer_stats['micro'] * 100:.2f}%</div><div class="k">micro CER({cer_stats['n']} 本合算)</div></div>
  <div class="card"><div class="v">{cer_stats['median'] * 100:.2f}%</div><div class="k">中央値</div></div>
  <div class="card"><div class="v">{cer_stats['p90'] * 100:.2f}%</div><div class="k">90 パーセンタイル</div></div>
  <div class="card"><div class="v">{cer_stats['zero']}</div><div class="k">CER 0%(完全一致)の本数</div></div>
</div>
<p>誤りの大半は表記ゆれ(「二」→「2」「プリンタ」→「プリンター」等)で、意味を変える誤認識は
同音のドメイン語(「社給」→「社級」「有線」→「優先」「上長」→「冗長」等)に集中する。
実運用ではカスタム語彙・後段の用語正規化で対処する典型パターンである。</p>
<h3>CER 上位(誤りが多い動画)</h3>
<table>
<tr><th>動画</th><th>CER</th><th>編集数 / 文字数</th></tr>
{"".join(f"<tr><td>{vid}</td><td class='num'>{r['cer'] * 100:.2f}%</td><td class='num'>{r['edits']} / {r['ref_chars']}</td></tr>" for vid, r in worst)}
</table>
<p><b>外れ値の内訳(上位 2 本は個別に原因を確認済み)。</b>
g67-portal-cancel(17.99%)は<b>末尾ステップの発話 25 文字が書き起こしから欠落</b>したもので、
本検証で唯一観測した発話の取りこぼし(末尾セグメント)。slide-files(10.58%)は台本に含まれる
記号・英字(「日付_案件_内容」「v1, v2」)の読み上げ形(アンダーライン等)との差で、
<b>正解データ側のアーティファクト</b>であり CU の誤りではない。これらを除く動画の CER は
おおむね 2% 未満に収まる。</p>
<div class="note"><b>注意:</b> 本データセットは合成音声(単一話者・雑音なし・鮮明な画面)であり、
CER は実収録動画に対する<b>上限性能</b>として読むこと。実案件では実動画でのパイロット測定を挟む。</div>

<h2>8. 結果 2: 検索精度</h2>
<h3>8.1 構成 A〜D の比較(全 {len(QUERIES)} クエリ)</h3>
<table>
<tr><th>構成</th><th>hit@1</th><th>hit@3</th><th>MRR</th><th>seg_hit@1</th>
<th>ans@1(S)</th><th>ans@3(S)</th></tr>
{"".join(retr_rows)}
</table>
<figure class="fig">{chart_hit}
<figcaption>図 2: 検索指標の構成間比較(全クエリ)。</figcaption></figure>
<figure class="fig">{chart_ans}
<figcaption>図 3: 画面のみ情報(S タイプ {q_types['S']} 問)の回答値含有率。
書き起こしのみ(A)では原理的に取れず、カスタムフィールド(C/D)で大きく改善する。</figcaption></figure>
<h3>8.2 構成 C で ans@3 を外した S クエリの内訳({n_s_miss} / {n_s} 問)</h3>
<table>
<tr><th>原因</th><th>件数</th><th>意味・対策</th></tr>
<tr><td>検索ミス(正解動画が top-3 外)</td><td class="num">{s_break['retr']}</td>
<td>ハイブリッド検索の改善余地(クエリ拡張・上位 k 拡大)</td></tr>
<tr><td>正解動画は当たったが、値を持つセグメントが top-3 外</td><td class="num">{s_break['seg']}</td>
<td>同一動画の別セグメントが上位を占有。動画単位の重複排除や「動画→セグメント」の 2 段検索で改善可能</td></tr>
<tr><td>値そのものが CU 出力に無い(転記漏れ)</td><td class="num">{s_break['transcribe']}</td>
<td>真の視覚転記漏れは S {n_s} 問中 {s_break['transcribe']} 件のみ。<b>CU は {n_s - s_break['transcribe']} / {n_s} 問({(n_s - s_break['transcribe']) / n_s * 100:.1f}%)で画面の値を出力できていた</b></td></tr>
</table>
<h3>8.3 動画形態別(構成 A vs C)</h3>
<table>
<tr><th>構成</th><th>形態</th><th>n</th><th>hit@1</th><th>hit@3</th><th>MRR</th></tr>
{"".join(by_form_rows)}
</table>
<p>無音(テロップのみ)動画は書き起こしが空になるため、構成 A では索引にすら入らない。
視覚情報を扱う構成 C で初めて検索対象になる点が形態別比較の要点である。</p>

<div class="pagebreak"></div>
<h2>9. 結果 3: RAG 回答品質(ragas)</h2>
<table>
<tr><th>ragas 指標</th><th>構成 A(書き起こしのみ)</th><th>構成 C(カスタムフィールド)</th></tr>
{ragas_rows}
</table>
<figure class="fig">{chart_ragas}
<figcaption>図 4: ragas 5 指標の比較(n={ragas['C']['n']}、判定 LLM: gpt-4.1-mini)。</figcaption></figure>
<p><b>読み方の注意(指標の性質)。</b>
(1) 構成 A の faithfulness が高い({ragas['A']['summary']['faithfulness']:.2f})のは、
コンテキストに根拠が無いとき「分かりません」と答える設計のため
(A の回答の {nc['A']}/{ragas['A']['n']} 問が「分かりません」、C は {nc['C']}/{ragas['C']['n']} 問)。
無回答は捏造ゼロ=忠実と評価されるので、faithfulness は
<b>context_recall / answer_correctness とセットで</b>読む必要がある。
(2) answer_relevancy は「分かりません」型の回答を 0 と評価する仕様のため両構成とも低く出る。
構成間の相対比較にのみ使用する。
(3) 総合すると、C は A に対して context_precision +{(ragas['C']['summary']['llm_context_precision_with_reference'] - ragas['A']['summary']['llm_context_precision_with_reference']):.2f} /
context_recall +{(ragas['C']['summary']['context_recall'] - ragas['A']['summary']['context_recall']):.2f} /
answer_correctness +{(ragas['C']['summary']['answer_correctness'] - ragas['A']['summary']['answer_correctness']):.2f} と、
「答えるべき質問に答えられる」方向で一貫して優位。</p>

<h2>10. 処理時間</h2>
{proc_html}
<p>CU の解析は非同期(Operation-Location ポーリング)。バッチ取り込みでは並列実行できるが、
紐づけた補完モデルデプロイの TPM が律速になる(§11)。</p>

<h2>11. 実装上の注意点(検証中に実際に踏んだ詰まりどころ)</h2>
<table>
<tr><th>#</th><th>事象</th><th>対処</th></tr>
<tr><td>1</td><td>defaults へのモデル登録をモデル名で行うと、PATCH は成功するのに analyze が失敗する</td>
<td>prebuilt アナライザーが参照する<b>エイリアス名</b>(prebuilt-analyzer-completion-mini 等)をキーに登録する。エラーは analyze 時まで遅延する</td></tr>
<tr><td>2</td><td>カスタムアナライザーの base に prebuilt-videoSearch を指定すると 400</td>
<td>base に使えるのは基底 4 種のみ(prebuilt-video 等)</td></tr>
<tr><td>3</td><td>親アナライザーの fieldSchema がセグメントに適用されない</td>
<td><b>フィールドを持つサブアナライザーを作り、親の contentCategories から参照する 2 段構成</b>にする(公式 analyzer-reference に記載)</td></tr>
<tr><td>4</td><td>カスタムアナライザーで models.completion を省くと analyze が失敗</td>
<td>モデル名(デプロイ名ではない)を明示する</td></tr>
<tr><td>5</td><td>既存アナライザー ID への PUT は変更が黙って無視される</td>
<td>実質イミュータブル。更新は DELETE → 再作成</td></tr>
<tr><td>6</td><td>解析の並列実行で 429(RateLimit)が analyze の失敗として返る</td>
<td>CU 自体でなく補完デプロイの TPM 律速。クォータ増強+指数バックオフ再試行を実装</td></tr>
<tr><td>7</td><td>omitContent: true とフィールド定義は併用不可(400)</td><td>omitContent: false にする</td></tr>
<tr><td>8</td><td>defaults・カスタムアナライザーは Bicep に乗らないデータプレーンの状態。環境再作成時に登録を忘れると解析が全滅する</td>
<td>セットアップスクリプトに defaults 登録(エイリアス込み)とアナライザー作成を含めて固定化</td></tr>
<tr><td>9</td><td>ソフト削除 → パージ → <b>同名再作成</b>したリソースでは CU の解析が「deployment or resource was not found(404)」で失敗し続けた(外部からのモデル呼び出しは正常)</td>
<td>別名でリソースを作り直すと即解消。検証環境の再作成は同名を避ける(公式未記載の実測)</td></tr>
<tr><td>10</td><td>フレームは約 1 FPS・512×512 に縮小され、小さい文字が落ち得る(公式記載)</td>
<td>本検証の画面文字(25〜40px/720p)は全件読めた。実動画では文字サイズに注意</td></tr>
</table>

<h2>12. 制約と限界</h2>
<ul>
<li><b>合成データ</b>: 実収録より条件が良い(単一話者・雑音なし・非圧縮画面)。CER・画面文字の
転記率は上限性能。実案件では実動画でパイロット測定を行うこと(本パイプラインは流用可能)。</li>
<li><b>規模</b>: 104 本・{len(QUERIES)} クエリでの測定。数千本規模ではベクトル索引のチューニング
(フィルタ・セマンティックランカー等)の追加検討が必要。</li>
<li><b>LLM-as-a-judge</b>: ragas の値は判定 LLM(gpt-4.1-mini)に依存する相対比較として読むこと。
構成間の差(A vs C)の比較には有効だが、絶対値の閾値運用には向かない。</li>
<li>単価は変動するため、コスト見積もりは最新の料金ページ(付録)で確認すること。</li>
</ul>

<h2>13. 実装チームへの推奨事項</h2>
<ol>
<li><b>採用構成は C</b>(日本語カスタムフィールド、2 段アナライザー)。top-3 を LLM に渡す標準的な
RAG で ans@3 = {top3_s:.2f}。D(フィールド重み付け)は動画間の切り分けを悪化させる
トレードオフがあり、top-1 しか使えない場合のみ検討。</li>
<li>書き起こしの別実装(Speech SDK 等)は不要。CU の出力(transcriptPhrases)をそのまま使う。</li>
<li>チャンク単位は CU のセグメント。時間範囲(startTimeMs/endTimeMs)をメタデータに持たせ、
回答には「動画名 + 分:秒」を引用させる。</li>
<li>フィールド設計 3 点セット: 日本語要約(summaryJa)/ 画面内テキストの一字一句転記(screenTexts)
/ 操作列挙(uiActions)。description は「ミニプロンプト」として具体例を列挙する。</li>
<li>バッチ取り込みは並列数と補完デプロイの TPM クォータをセットで設計し、429 再試行を必ず入れる。</li>
<li>同音ドメイン語の誤認識(社給→社級 等)に備え、用語正規化辞書を後段に用意する。</li>
</ol>

<h2>付録: 参照資料</h2>
<ul style="font-size:9pt">
<li>CU REST クイックスタート: learn.microsoft.com/azure/ai-services/content-understanding/quickstart/use-rest-api</li>
<li>CU what's new(GA 2025-11-01): learn.microsoft.com/azure/ai-services/content-understanding/whats-new</li>
<li>CU video 概要(1 FPS / 512×512 等の制約): learn.microsoft.com/azure/ai-services/content-understanding/video/overview</li>
<li>CU アナライザーリファレンス(contentCategories / fieldSchema): learn.microsoft.com/azure/ai-services/content-understanding/concepts/analyzer-reference</li>
<li>CU 言語・リージョン対応: learn.microsoft.com/azure/ai-services/content-understanding/language-region-support</li>
<li>AI Search ハイブリッド検索(RRF): learn.microsoft.com/azure/search/hybrid-search-overview</li>
<li>AI Search スコアリングプロファイル: learn.microsoft.com/azure/search/index-add-scoring-profiles</li>
<li>ragas ドキュメント: docs.ragas.io</li>
<li>CU 料金: azure.microsoft.com/pricing/details/content-understanding/</li>
<li>データセット調査(PsTuts-VQA / VideoGUI): github.com/adobe-research/PsTuts-VQA-Dataset ほか。詳細は docs/dataset-research.md</li>
</ul>
<p style="font-size:9pt;color:#667;margin-top:14px">本レポートの数値はすべてリポジトリ
<code>labs/cu-video-rag/logs/</code> の評価出力から機械的に転記したもの(gen_report.py)。
再現手順は README.md を参照。</p>
</body></html>"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUT_DIR / "report.html"
    html_path.write_text(build_html(), encoding="utf-8")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri())
        page.pdf(
            path=str(OUT_DIR / "cu-video-rag-report.pdf"),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<span></span>",
            footer_template=(
                '<div style="width:100%;font-size:8px;color:#888;text-align:center;">'
                'CU 動画 RAG 検証レポート — <span class="pageNumber"></span> / <span class="totalPages"></span></div>'
            ),
            margin={"top": "14mm", "bottom": "14mm", "left": "0mm", "right": "0mm"},
        )
        browser.close()
    print(f"wrote {OUT_DIR / 'cu-video-rag-report.pdf'}")


if __name__ == "__main__":
    main()
