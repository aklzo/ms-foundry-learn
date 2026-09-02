"""データセット全体の集約(コア 5 + コア拡張 9 + 生成 90 = 104 本)。

パイプライン(record / run_pipeline)はこのモジュールの SCENARIOS / QUERIES を正とする。
生成コーパスはシード固定(42)で決定的。
"""

from __future__ import annotations

from .gen_scenarios import generate_corpus
from .scenarios import QUERIES as QUERIES_CORE
from .scenarios import SCENARIOS as SCENARIOS_CORE
from .scenarios_ext import QUERIES_EXT, SCENARIOS_EXT

_GEN_SCENARIOS, _GEN_QUERIES = generate_corpus(seed=42)

SCENARIOS = SCENARIOS_CORE + SCENARIOS_EXT + _GEN_SCENARIOS
QUERIES = QUERIES_CORE + QUERIES_EXT + _GEN_QUERIES

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


def validate() -> list[str]:
    """データセットの整合性チェック(id 重複・クエリ参照・answer 衝突)。"""
    problems = []
    ids = [s.id for s in SCENARIOS]
    if len(ids) != len(set(ids)):
        problems.append("duplicate scenario ids")
    idset = set(ids)
    qids = [q["qid"] for q in QUERIES]
    if len(qids) != len(set(qids)):
        problems.append("duplicate qids")
    for q in QUERIES:
        if q["video"] not in idset:
            problems.append(f"{q['qid']}: unknown video {q['video']}")
        sc = next(s for s in SCENARIOS if s.id == q["video"])
        if not (0 <= q["expected_step"] < len(sc.steps)):
            problems.append(f"{q['qid']}: expected_step out of range")
        if "ref_answer" not in q:
            problems.append(f"{q['qid']}: missing ref_answer")
    return problems


if __name__ == "__main__":
    from collections import Counter

    print("scenarios:", len(SCENARIOS), Counter(FORM_OF_VIDEO.values()))
    print("queries:", len(QUERIES), Counter(q["type"] for q in QUERIES))
    print("problems:", validate() or "none")
