"""評価: 書き起こし CER と検索指標(hit@k / MRR / セグメント時刻ヒット / ans@k)ほか。

- CER = 文字単位の編集距離 / 正解文字数。正規化は NFKC + 空白・主要句読点の除去
  (句読点の切り方は STT の流儀差であり意味理解に影響しないため)
- 検索: クエリごとにハイブリッド top-5 →
    video hit@1/@3(正解動画のチャンクが 1 位 / 3 位以内に出るか)
    MRR(正解動画の最初の順位の逆数)
    segment hit@1(1 位チャンクが正解動画かつ正解ステップの時間範囲と重なるか)
    ans@1/@3(**正解動画の**チャンクの本文に回答値そのものが含まれるか。動画を問わない
      旧定義 ans@3(any) は値の衝突で過大評価されるため参考値に格下げ)
  N(ナレーション由来)/ S(画面のみ)/ C(紛らわしい)のタイプ別に集計する
- 追加指標(ラウンド 3):
    paired_bootstrap   構成間差の 95% 信頼区間(同一クエリ集合の対応ありブートストラップ)
    eval_segmentation  CU セグメント境界と正解ステップ境界の一致(±tol 秒の P/R/F1)
    eval_fact_transcription  画面のみ情報の値が CU 出力に転記されたか(検索を介さない直接測定)
    eval_abstention    根拠の無い質問(U タイプ)への棄権率(捏造の有無)
"""

from __future__ import annotations

import random
import re
import unicodedata

_PUNCT = re.compile(r"[\s、。,.!?!?・:「」()()]")
ABSTAIN_MARK = "分かりません"


def normalize(text: str) -> str:
    return _PUNCT.sub("", unicodedata.normalize("NFKC", text))


def edit_distance(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        return 0.0
    return edit_distance(ref, hyp) / len(ref)


def eval_transcripts(ground_truths: dict[str, dict], hypotheses: dict[str, str]) -> dict:
    """video_id → (正解 full_transcript, CU 書き起こし) の CER。CU 結果が無い動画は missing に記録。"""
    rows = {}
    missing = []
    total_edits = 0
    total_chars = 0
    for vid, gt in ground_truths.items():
        ref = normalize(gt["full_transcript"])
        if not ref:  # 無音(テロップのみ)動画は CER の対象外
            continue
        if vid not in hypotheses:
            missing.append(vid)
            continue
        hyp = normalize(hypotheses[vid])
        d = edit_distance(ref, hyp)
        rows[vid] = {"cer": round(d / len(ref), 4), "ref_chars": len(ref), "edits": d}
        total_edits += d
        total_chars += len(ref)
    return {
        "per_video": rows,
        "micro_cer": round(total_edits / total_chars, 4) if total_chars else 0.0,
        "missing": missing,
    }


def eval_retrieval(
    queries: list[dict],
    ground_truths: dict[str, dict],
    search_fn,
    top: int = 5,
    form_of_video: dict[str, str] | None = None,
) -> dict:
    """search_fn(query_text) -> ランク付きチャンク列 [{video_id, start_s, end_s, content, ...}]"""
    per_query = []
    for q in queries:
        if q.get("type") == "U":  # 根拠なし質問は検索指標の対象外
            continue
        hits = search_fn(q["text"])[:top]
        expected_video = q["video"]
        step = ground_truths[expected_video]["steps"][q["expected_step"]]
        rank = next(
            (i + 1 for i, h in enumerate(hits) if h["video_id"] == expected_video), None
        )
        seg_hit = bool(
            hits
            and hits[0]["video_id"] == expected_video
            and hits[0]["start_s"] < step["end_s"]
            and hits[0]["end_s"] > step["start_s"]
        )
        row = {
            "qid": q["qid"],
            "type": q["type"],
            "rank": rank,
            "hit1": rank == 1,
            "hit3": rank is not None and rank <= 3,
            "seg_hit1": seg_hit,
            "top1": f"{hits[0]['video_id']}[{hits[0]['start_s']:.0f}-{hits[0]['end_s']:.0f}s]" if hits else "-",
            "top3_videos": [h["video_id"] for h in hits[:3]],
        }
        # 回答含有率: 正解動画のチャンク本文に回答文字列が含まれるか(検索が当たっても
        # 本文に値が無ければ RAG は回答を生成できない、を測る)。動画を問わない旧定義は
        # 別動画の同じ値(例: 同じ締め日)で誤ってヒットするため ans3_any として参考記録のみ
        if "answer" in q:
            ans = normalize(q["answer"])

            def _has(h, _ans=ans, _vid=expected_video):
                return h["video_id"] == _vid and _ans in normalize(h["content"])

            row["ans1"] = bool(hits) and _has(hits[0])
            row["ans3"] = any(_has(h) for h in hits[:3])
            row["ans3_any"] = any(ans in normalize(h["content"]) for h in hits[:3])
        if form_of_video:
            row["form"] = form_of_video.get(expected_video, "?")
        per_query.append(row)

    def agg(rows: list[dict]) -> dict:
        n = len(rows)
        if not n:
            return {}
        out = {
            "n": n,
            "hit@1": round(sum(r["hit1"] for r in rows) / n, 3),
            "hit@3": round(sum(r["hit3"] for r in rows) / n, 3),
            "mrr": round(sum(1 / r["rank"] if r["rank"] else 0 for r in rows) / n, 3),
            "seg_hit@1": round(sum(r["seg_hit1"] for r in rows) / n, 3),
        }
        ans_rows = [r for r in rows if "ans1" in r]
        if ans_rows:
            out["ans@1"] = round(sum(r["ans1"] for r in ans_rows) / len(ans_rows), 3)
            out["ans@3"] = round(sum(r["ans3"] for r in ans_rows) / len(ans_rows), 3)
            out["ans@3_any"] = round(sum(r["ans3_any"] for r in ans_rows) / len(ans_rows), 3)
        return out

    by_type = {t: agg([r for r in per_query if r["type"] == t]) for t in ("N", "S", "C")}
    out = {"overall": agg(per_query), "by_type": by_type, "per_query": per_query}
    if form_of_video:
        forms = sorted({r.get("form") for r in per_query if r.get("form")})
        out["by_form"] = {f: agg([r for r in per_query if r.get("form") == f]) for f in forms}
    return out


# ---------------------------------------------------------------- 構成間比較(信頼区間)

_METRIC_KEYS = {"hit@1": "hit1", "hit@3": "hit3", "seg_hit@1": "seg_hit1", "ans@1": "ans1", "ans@3": "ans3"}


def _metric_value(row: dict, metric: str):
    if metric == "mrr":
        return (1 / row["rank"]) if row.get("rank") else 0.0
    key = _METRIC_KEYS[metric]
    return float(row[key]) if key in row else None


def paired_bootstrap(rows_a: list[dict], rows_b: list[dict], metric: str, n_boot: int = 2000, seed: int = 0) -> dict:
    """同一クエリ集合での構成 B − 構成 A の平均差と 95% 信頼区間(対応ありブートストラップ)。"""
    a = {r["qid"]: r for r in rows_a}
    b = {r["qid"]: r for r in rows_b}
    pairs = []
    for qid in a:
        if qid not in b:
            continue
        va, vb = _metric_value(a[qid], metric), _metric_value(b[qid], metric)
        if va is None or vb is None:
            continue
        pairs.append((va, vb))
    n = len(pairs)
    if n == 0:
        return {}
    diffs = [vb - va for va, vb in pairs]
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        boots.append(sum(diffs[rng.randrange(n)] for _ in range(n)) / n)
    boots.sort()
    lo, hi = boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]
    return {
        "n": n,
        "mean_a": round(sum(va for va, _ in pairs) / n, 3),
        "mean_b": round(sum(vb for _, vb in pairs) / n, 3),
        "diff": round(sum(diffs) / n, 3),
        "ci95": [round(lo, 3), round(hi, 3)],
        "significant": not (lo <= 0 <= hi),
    }


def compare_configs(eval_a: dict, eval_b: dict, metrics=("hit@1", "hit@3", "mrr", "seg_hit@1"), s_metrics=("ans@1", "ans@3")) -> dict:
    rows_a, rows_b = eval_a["per_query"], eval_b["per_query"]
    out = {m: paired_bootstrap(rows_a, rows_b, m) for m in metrics}
    sa = [r for r in rows_a if r["type"] == "S"]
    sb = [r for r in rows_b if r["type"] == "S"]
    for m in s_metrics:
        out[f"{m}(S)"] = paired_bootstrap(sa, sb, m)
    return out


# ---------------------------------------------------------------- セグメント分割の質

def eval_segmentation(
    ground_truths: dict[str, dict],
    segments_by_video: dict[str, list[dict]],
    tol_s: float = 2.0,
    form_of_video: dict[str, str] | None = None,
) -> dict:
    """CU セグメント境界(2 番目以降の開始時刻)と正解ステップ境界の一致率。

    recall = 正解境界のうち ±tol 秒以内に CU 境界があるもの / 正解境界数
    precision = CU 境界のうち ±tol 秒以内に正解境界があるもの / CU 境界数
    """
    per_video = {}
    for vid, segs in segments_by_video.items():
        gt = ground_truths.get(vid)
        if not gt:
            continue
        gt_b = [s["start_s"] for s in gt["steps"][1:]]
        cu_b = [s["start_s"] for s in segs[1:]]
        dur = gt["duration_s"]
        covered = sum(s["end_s"] - s["start_s"] for s in segs)
        head_gap = segs[0]["start_s"] if segs else dur
        tail_gap = dur - segs[-1]["end_s"] if segs else dur
        per_video[vid] = {
            "n_steps": len(gt["steps"]),
            "n_segments": len(segs),
            "gt_boundaries": len(gt_b),
            "cu_boundaries": len(cu_b),
            "matched_gt": sum(1 for g in gt_b if any(abs(g - c) <= tol_s for c in cu_b)),
            "matched_cu": sum(1 for c in cu_b if any(abs(g - c) <= tol_s for g in gt_b)),
            # セグメントが動画の時間軸をどれだけ覆うか。先頭セグメントより前で始まるフレーズは
            # 出力から消える(findings 1-13)ので head_gap が主指標。末尾はキーフレーム格子で
            # 発話終端より数秒早く切れるのが常態(それ自体は欠落ではない)
            "coverage": round(covered / dur, 3) if dur else 0.0,
            "head_gap_s": round(head_gap, 2),
            "tail_gap_s": round(max(tail_gap, 0.0), 2),
            "form": (form_of_video or {}).get(vid, "?"),
        }

    def agg(rows):
        if not rows:
            return {}
        gt_n = sum(r["gt_boundaries"] for r in rows)
        cu_n = sum(r["cu_boundaries"] for r in rows)
        rec = sum(r["matched_gt"] for r in rows) / gt_n if gt_n else 0.0
        prec = sum(r["matched_cu"] for r in rows) / cu_n if cu_n else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        return {
            "videos": len(rows),
            "steps": sum(r["n_steps"] for r in rows),
            "segments": sum(r["n_segments"] for r in rows),
            "segments_per_step": round(sum(r["n_segments"] for r in rows) / sum(r["n_steps"] for r in rows), 3),
            "boundary_recall": round(rec, 3),
            "boundary_precision": round(prec, 3),
            "boundary_f1": round(f1, 3),
            "coverage_mean": round(sum(r["coverage"] for r in rows) / len(rows), 3),
            "coverage_min": min(r["coverage"] for r in rows),
            "videos_with_head_gap_over_3s": sum(1 for r in rows if r["head_gap_s"] > 3),
        }

    rows = list(per_video.values())
    forms = sorted({r["form"] for r in rows})
    return {
        "tol_s": tol_s,
        "overall": agg(rows),
        "by_form": {f: agg([r for r in rows if r["form"] == f]) for f in forms},
        "head_gaps": sorted(
            [{"video": v, **{k: r[k] for k in ("coverage", "head_gap_s", "tail_gap_s")}} for v, r in per_video.items() if r["head_gap_s"] > 3],
            key=lambda x: x["coverage"],
        ),
        "per_video": per_video,
    }


def transcript_divergence(cer_a: dict, cer_b: dict, seg_a: dict | None = None, seg_b: dict | None = None, threshold: float = 0.05) -> list[dict]:
    """同一音声を 2 つのアナライザーで書き起こした CER の差が threshold を超える動画
    (= 実行依存の発話欠落の検出。findings 1-13)。seg_* は eval_segmentation の per_video。"""
    out = []
    for vid, ra in cer_a.get("per_video", {}).items():
        rb = cer_b.get("per_video", {}).get(vid)
        if not rb:
            continue
        diff = ra["cer"] - rb["cer"]
        if abs(diff) > threshold:
            row = {"video": vid, "cer_a": ra["cer"], "cer_b": rb["cer"], "diff": round(diff, 4)}
            for label, seg in (("a", seg_a), ("b", seg_b)):
                pv = (seg or {}).get("per_video", {}).get(vid)
                if pv:
                    row[f"head_gap_{label}"] = pv["head_gap_s"]
                    row[f"tail_gap_{label}"] = pv["tail_gap_s"]
                    row[f"segments_{label}"] = pv["n_segments"]
            out.append(row)
    return sorted(out, key=lambda r: -abs(r["diff"]))


# ---------------------------------------------------------------- 画面のみ情報の転記率(直接測定)

def eval_fact_transcription(facts: list[dict], segments_by_video: dict[str, list[dict]]) -> dict:
    """facts: [{video, key, value, start_s, end_s, form}]。
    found_any: どこかのセグメントの生成フィールドに値がある / found_in_step: 表示区間と重なるセグメントにある /
    found_in_transcript: 書き起こしにも出ている(=画面のみ情報になっていない、の検査)"""
    rows = []
    for f in facts:
        segs = segments_by_video.get(f["video"], [])
        val = normalize(f["value"])
        in_any = [s for s in segs if val in normalize(" ".join(s["fields"].values()))]
        in_step = [s for s in in_any if s["start_s"] < f["end_s"] and s["end_s"] > f["start_s"]]
        rows.append(
            {
                **f,
                "found_any": bool(in_any),
                "found_in_step": bool(in_step),
                "found_in_transcript": any(val in normalize(s["transcript"]) for s in segs),
            }
        )

    def agg(rs):
        n = len(rs)
        if not n:
            return {}
        return {
            "n": n,
            "found_any": round(sum(r["found_any"] for r in rs) / n, 3),
            "found_in_step": round(sum(r["found_in_step"] for r in rs) / n, 3),
            "found_in_transcript": round(sum(r["found_in_transcript"] for r in rs) / n, 3),
        }

    forms = sorted({r.get("form", "?") for r in rows})
    return {
        "overall": agg(rows),
        "by_form": {f: agg([r for r in rows if r.get("form") == f]) for f in forms},
        "missing": [{"video": r["video"], "key": r["key"], "value": r["value"]} for r in rows if not r["found_any"]],
        "rows": rows,
    }


# ---------------------------------------------------------------- 棄権率(根拠なし質問)

def eval_abstention(answers: list[dict]) -> dict:
    """answers: rag_answers_*.json の行([{qid, type, answer, ...}])。"""

    def rate(rows):
        n = len(rows)
        return {"n": n, "abstain_rate": round(sum(ABSTAIN_MARK in r["answer"] for r in rows) / n, 3)} if n else {}

    u = [r for r in answers if r["type"] == "U"]
    a = [r for r in answers if r["type"] != "U"]
    return {
        "unanswerable": {**rate(u), "answered_anyway": [r["qid"] for r in u if ABSTAIN_MARK not in r["answer"]]},
        "answerable": rate(a),
        "answerable_by_type": {t: rate([r for r in a if r["type"] == t]) for t in ("N", "S", "C")},
    }


def format_table(results_by_config: dict[str, dict]) -> str:
    """構成別の集計を markdown 表にする(docs へ転記する一次出力)。"""
    lines = [
        "| 構成 | 対象 | n | hit@1 | hit@3 | MRR | seg_hit@1 | ans@1 | ans@3 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for config, res in results_by_config.items():
        rows = [("全体", res["overall"])] + [
            (f"タイプ {t}", res["by_type"][t]) for t in ("N", "S", "C")
        ]
        for label, m in rows:
            if m:
                ans1 = f"{m['ans@1']:.3f}" if "ans@1" in m else "-"
                ans3 = f"{m['ans@3']:.3f}" if "ans@3" in m else "-"
                lines.append(
                    f"| {config} | {label} | {m['n']} | {m['hit@1']:.3f} | {m['hit@3']:.3f} "
                    f"| {m['mrr']:.3f} | {m['seg_hit@1']:.3f} | {ans1} | {ans3} |"
                )
    return "\n".join(lines)
