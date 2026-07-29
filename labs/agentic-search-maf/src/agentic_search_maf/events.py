"""Progress events emitted by the workflow, ported from ``events.rs``.

The Rust version delivered these through an ``EventSink`` callback because
the core had no event infrastructure of its own. MAF workflows have one
built in: executors call ``ctx.add_event(...)`` and frontends consume the
stream from ``workflow.run_stream(...)``. The payload models and the JSONL
trace format are kept identical to the Rust version so traces stay
comparable across the two implementations.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from .schemas import Evaluation


class PlanReady(BaseModel):
    type: Literal["plan_ready"] = "plan_ready"
    queries: list[str]


class QueryStarted(BaseModel):
    type: Literal["query_started"] = "query_started"
    query: str


class PageProcessed(BaseModel):
    type: Literal["page_processed"] = "page_processed"
    url: str
    new_findings: int


class IterationDone(BaseModel):
    type: Literal["iteration_done"] = "iteration_done"
    iteration: int
    new_findings: int
    total_findings: int


class EvaluationDone(BaseModel):
    """Carries the full evaluation (scores, per-axis issues, follow-up
    queries) so audits can show *why* the agent kept searching."""

    type: Literal["evaluation_done"] = "evaluation_done"
    iteration: int
    evaluation: Evaluation


AgentEventPayload = PlanReady | QueryStarted | PageProcessed | IterationDone | EvaluationDone

_PAYLOAD_ADAPTER: TypeAdapter = TypeAdapter(
    Annotated[AgentEventPayload, Field(discriminator="type")]
)


class TraceRecord(BaseModel):
    """An event stamped with its occurrence time; one JSON line per record
    in persisted trace files."""

    timestamp: datetime
    event: AgentEventPayload

    @classmethod
    def now(cls, event: AgentEventPayload) -> TraceRecord:
        return cls(timestamp=datetime.now().astimezone(), event=event)


def to_jsonl(records: list[TraceRecord]) -> str:
    """Serialize records as JSON Lines (one flattened object per line, same
    shape as the Rust version's ``#[serde(flatten)]``)."""
    lines = []
    for record in records:
        flat = {
            "timestamp": record.timestamp.isoformat(),
            **record.event.model_dump(),
        }
        lines.append(json.dumps(flat, ensure_ascii=False))
    return "\n".join(lines)


def from_jsonl(text: str) -> list[TraceRecord]:
    """Parse JSON Lines back into records, skipping unparseable lines so a
    partially corrupted trace file still renders."""
    records: list[TraceRecord] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            timestamp = data.pop("timestamp")
            event = _PAYLOAD_ADAPTER.validate_python(data)
            records.append(TraceRecord(timestamp=datetime.fromisoformat(timestamp), event=event))
        except Exception:
            continue
    return records
