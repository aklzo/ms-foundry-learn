"""評価: 書き起こし CER と検索指標(hit@k / MRR / セグメント時刻ヒット)。

- CER = 文字単位の編集距離 / 正解文字数。正規化は NFKC + 空白・主要句読点の除去
  (句読点の切り方は STT の流儀差であり意味理解に影響しないため)
- 検索: クエリごとにハイブリッド top-5 →
    video hit@1/@3(正解動画のチャンクが 1 位 / 3 位以内に出るか)
    MRR(正解動画の最初の順位の逆数)
    segment hit@1(1 位チャンクが正解動画かつ正解ステップの時間範囲と重なるか)
  N(ナレーション由来)/ S(画面のみ)/ C(紛らわしい)のタイプ別に集計する
"""

from __future__ import annotations

import re
import unicodedata

_PUNCT = re.compile(r"[\s、。,.!?!?・:「」()()]")


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
    """video_id → (正解 full_transcript, CU 書き起こし) の CER。"""
    rows = {}
    total_edits = 0
    total_chars = 0
    for vid, gt in ground_truths.items():
        ref = normalize(gt["full_transcript"])
        hyp = normalize(hypotheses.get(vid, ""))
        d = edit_distance(ref, hyp)
        rows[vid] = {"cer": round(d / len(ref), 4), "ref_chars": len(ref), "edits": d}
        total_edits += d
        total_chars += len(ref)
    return {"per_video": rows, "micro_cer": round(total_edits / total_chars, 4) if total_chars else 0.0}


def eval_retrieval(
    queries: list[dict],
    ground_truths: dict[str, dict],
    search_fn,
    top: int = 5,
) -> dict:
    """search_fn(query_text) -> ランク付きチャンク列 [{video_id, start_s, end_s, ...}]"""
    per_query = []
    for q in queries:
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
        }
        # 回答含有率: 取得チャンク本文に回答文字列が含まれるか(検索が当たっても
        # 本文に値が無ければ RAG は回答を生成できない、を測る)
        if "answer" in q:
            ans = normalize(q["answer"])
            row["ans1"] = bool(hits) and ans in normalize(hits[0]["content"])
            row["ans3"] = any(ans in normalize(h["content"]) for h in hits[:3])
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
        return out

    by_type = {t: agg([r for r in per_query if r["type"] == t]) for t in ("N", "S", "C")}
    return {"overall": agg(per_query), "by_type": by_type, "per_query": per_query}


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
