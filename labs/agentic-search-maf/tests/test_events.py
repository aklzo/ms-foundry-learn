from agentic_search_maf.events import (
    EvaluationDone,
    PlanReady,
    QueryStarted,
    TraceRecord,
    from_jsonl,
    to_jsonl,
)
from agentic_search_maf.schemas import Evaluation


def test_trace_records_roundtrip_through_jsonl():
    records = [
        TraceRecord.now(PlanReady(queries=["q1", "q2"])),
        TraceRecord.now(QueryStarted(query="q1")),
        TraceRecord.now(EvaluationDone(iteration=1, evaluation=Evaluation())),
    ]
    jsonl = to_jsonl(records)
    assert len(jsonl.splitlines()) == 3
    assert '"type": "plan_ready"' in jsonl

    parsed = from_jsonl(jsonl)
    assert len(parsed) == 3
    assert isinstance(parsed[1].event, QueryStarted)


def test_from_jsonl_skips_corrupted_lines():
    jsonl = (
        'not json\n{"timestamp":"2026-06-11T00:00:00+09:00","type":"query_started","query":"q"}\n'
    )
    parsed = from_jsonl(jsonl)
    assert len(parsed) == 1
