"""Serializable, append-only diagnostics for one Tara run.

Traces intentionally complement WorkingMemory: memory is bounded operational
state while a trace is the chronological account that can be saved or replayed.
"""
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


SENSITIVE_MARKER = "<REDACTED>"


def sanitize_trace_data(value: Any, sensitive: bool = False) -> Any:
    """Return JSON-safe diagnostics without credential values.

    Callers mark a password action as sensitive.  Key-name filtering is a
    second defensive boundary for diagnostics supplied by integrations.
    """
    if sensitive:
        return SENSITIVE_MARKER
    if isinstance(value, dict):
        return {
            str(key): (SENSITIVE_MARKER if any(token in str(key).lower()
                                               for token in ("password", "secret", "token", "credential"))
                       else sanitize_trace_data(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_trace_data(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "model_dump"):
        return sanitize_trace_data(value.model_dump())
    return str(value)


class FailureRecord(BaseModel):
    category: str
    error_type: str = ""
    step: int = 0
    goal_id: Optional[int] = None
    action: Dict[str, Any] = Field(default_factory=dict)
    recovery_strategy: str = ""
    recovered: bool = False


class TraceEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    step: int = 0
    event_type: str
    goal_id: Optional[int] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class RunSummary(BaseModel):
    run_id: str
    task: str
    result: str = "UNKNOWN"
    total_steps: int = 0
    completed_goals: int = 0
    failed_goals: int = 0
    planner_calls: int = 0
    deterministic_decisions: int = 0
    fallbacks: int = 0
    recovery_count: int = 0
    no_progress_count: int = 0
    repeated_action_count: int = 0
    facts_discovered: int = 0
    checkpoints_created: int = 0
    checkpoints_restored: int = 0
    duration_seconds: float = 0.0
    active_page_count: int = 0
    stale_target_events: int = 0
    failures: List[FailureRecord] = Field(default_factory=list)


class AgentTrace(BaseModel):
    trace_version: int = 1
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    task: str = ""
    events: List[TraceEvent] = Field(default_factory=list)

    def record(self, event_type: str, step: int = 0, goal_id: Optional[int] = None,
               sensitive: bool = False, **data: Any) -> TraceEvent:
        # Preserve event metadata (action kind, step, target) while removing
        # only the sensitive payload. Passing the entire event through the
        # redactor would turn ``data`` into a scalar and lose diagnostics.
        if sensitive:
            data = dict(data)
            action = data.get("action")
            if isinstance(action, dict):
                action = dict(action)
                if "text" in action:
                    action["text"] = SENSITIVE_MARKER
                data["action"] = action
            data["sensitive"] = True
        event = TraceEvent(event_type=event_type, step=step, goal_id=goal_id,
                           data=sanitize_trace_data(data))
        self.events.append(event)
        return event

    def export_json(self, **kwargs: Any) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False, **kwargs)

    def save(self, directory: str = ".tara/traces") -> str:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{self.run_id}.json"
        fd, temporary = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=target)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(self.export_json())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return str(path)

    @classmethod
    def load(cls, path: str) -> "AgentTrace":
        with Path(path).open(encoding="utf-8") as handle:
            trace = cls.model_validate(json.load(handle))
        if trace.trace_version != 1:
            raise ValueError("Unsupported trace version.")
        return trace
