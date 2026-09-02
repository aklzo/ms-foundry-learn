"""データセット全体の集約(コア 5 + コア拡張 9 + 生成 90 = 104 本)。

パイプライン(record / run_pipeline)はこのモジュールの SCENARIOS / QUERIES を正とする。
生成コーパスはシード固定(42)で決定的。

- QUERIES     : 正解動画のある評価クエリ(N/S/C。検索指標・ragas の対象)
- QUERIES_U   : コーパスに根拠が無い質問(U。棄権率の測定にのみ使う)
- ALL_QUERIES : 回答生成(rag-answer)の対象 = QUERIES + QUERIES_U
"""

from __future__ import annotations

import json

from .gen_scenarios import generate_corpus
from .scenarios import QUERIES as QUERIES_CORE
from .scenarios import SCENARIOS as SCENARIOS_CORE
from .scenarios import Scenario
from .scenarios_ext import QUERIES_EXT, QUERIES_UNANSWERABLE, SCENARIOS_EXT

_GEN_SCENARIOS, _GEN_QUERIES = generate_corpus(seed=42)

SCENARIOS = SCENARIOS_CORE + SCENARIOS_EXT + _GEN_SCENARIOS
QUERIES = QUERIES_CORE + QUERIES_EXT + _GEN_QUERIES
QUERIES_U = QUERIES_UNANSWERABLE
ALL_QUERIES = QUERIES + QUERIES_U

# 形態の分類(レポート・集計用)
FORM_OF_VIDEO: dict[str, str] = {}
for sc in SCENARIOS:
    if sc.id.startswith("slide-") or sc.id == "security-basics":
        FORM_OF_VIDEO[sc.id] = "slide"  # スライド講義型
    elif all(not s.narration for s in sc.steps):
        FORM_OF_VIDEO[sc.id] = "silent"  # 無音・テロップのみ
    elif len(sc.steps) >= 8:
        FORM_OF_VIDEO[sc.id] = "long"  # 長尺・複数章
    else:
        FORM_OF_VIDEO[sc.id] = "narrated"  # ナレーション付き UI 操作


def scenario_text(sc: Scenario) -> str:
    """動画に出る全テキスト(ナレーション+画面 op)。値の衝突検査に使う。"""
    parts = [sc.title, sc.app_name]
    for st in sc.steps:
        parts.append(st.narration)
        parts.extend(json.dumps(op, ensure_ascii=False) for op in st.ops)
    return "\n".join(parts)


def fact_positions() -> list[dict]:
    """画面のみ情報(screen_only_facts)ごとに、値が表示されるステップ index を解決する。

    戻り値: [{video, key, value, steps: [index...], form}]。値が画面 op に出るステップが
    見つからない場合は steps=[](設計上は起きない。validate で検出)。
    """
    out = []
    for sc in SCENARIOS:
        for key, value in sc.screen_only_facts.items():
            steps = [
                i for i, st in enumerate(sc.steps)
                if any(value in json.dumps(op, ensure_ascii=False) for op in st.ops)
            ]
            out.append({"video": sc.id, "key": key, "value": value, "steps": steps, "form": FORM_OF_VIDEO[sc.id]})
    return out


def validate() -> list[str]:
    """データセットの整合性チェック(id 重複・クエリ参照・answer 衝突・U クエリ)。"""
    from .evaluate import normalize

    problems = []
    ids = [s.id for s in SCENARIOS]
    if len(ids) != len(set(ids)):
        problems.append("duplicate scenario ids")
    idset = set(ids)
    qids = [q["qid"] for q in ALL_QUERIES]
    if len(qids) != len(set(qids)):
        problems.append("duplicate qids")
    texts = {sc.id: normalize(scenario_text(sc)) for sc in SCENARIOS}
    for q in QUERIES:
        if q["video"] not in idset:
            problems.append(f"{q['qid']}: unknown video {q['video']}")
            continue
        sc = next(s for s in SCENARIOS if s.id == q["video"])
        if not (0 <= q["expected_step"] < len(sc.steps)):
            problems.append(f"{q['qid']}: expected_step out of range")
        if "ref_answer" not in q:
            problems.append(f"{q['qid']}: missing ref_answer")
        if q["type"] == "S":
            if "answer" not in q:
                problems.append(f"{q['qid']}: S query without answer")
                continue
            ans = normalize(q["answer"])
            if ans not in texts[q["video"]]:
                problems.append(f"{q['qid']}: answer {q['answer']!r} not shown in {q['video']}")
            others = [vid for vid, t in texts.items() if vid != q["video"] and ans in t]
            if others:
                problems.append(f"{q['qid']}: answer {q['answer']!r} also appears in {others}")
    for q in QUERIES_U:
        if q.get("type") != "U" or "video" in q:
            problems.append(f"{q['qid']}: U query must have type U and no video")
    for f in fact_positions():
        if not f["steps"]:
            problems.append(f"{f['video']}: fact {f['key']}={f['value']!r} not displayed in any step")
    return problems


if __name__ == "__main__":
    from collections import Counter

    print("scenarios:", len(SCENARIOS), Counter(FORM_OF_VIDEO.values()))
    print("queries:", len(QUERIES), Counter(q["type"] for q in QUERIES), "+ unanswerable", len(QUERIES_U))
    print("problems:", validate() or "none")
