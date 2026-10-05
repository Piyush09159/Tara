"""Deterministic replay of safe, recorded browser actions."""
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from agent.action import BrowserAction
from agent.trace import AgentTrace, SENSITIVE_MARKER


class ReplayResult(BaseModel):
    success: bool
    executed_steps: int = 0
    divergences: List[Dict[str, Any]] = Field(default_factory=list)


class TraceReplayer:
    """Replay action_selected records against a freshly observed browser.

    Browser actions are reconstructed from data, never from live locator or
    Playwright references. Redacted input can never be replayed by default.
    """
    def __init__(self, reader, actions):
        self.reader = reader
        self.actions = actions

    def replay(self, trace: AgentTrace) -> ReplayResult:
        executed = 0
        for event in trace.events:
            if event.event_type != "action_selected":
                continue
            expected = event.data.get("action", {})
            if expected.get("text") == SENSITIVE_MARKER or event.data.get("sensitive"):
                return ReplayResult(success=False, executed_steps=executed, divergences=[{
                    "step": event.step, "reason": "sensitive_action_not_replayable",
                    "expected_action": expected,
                }])
            try:
                current = self.reader.read_page()
                action = BrowserAction.model_validate(expected)
                if action.element_id and not any(item.id == action.element_id and item.visible and item.enabled
                                                 for item in (list(current.links) + list(current.buttons) + list(current.inputs))):
                    raise ValueError("recorded target is absent from current page")
                outcome = self.actions.execute(action)
                if not outcome.get("success"):
                    raise ValueError(outcome.get("error", outcome.get("error_type", "action failed")))
                executed += 1
            except Exception as error:
                return ReplayResult(success=False, executed_steps=executed, divergences=[{
                    "step": event.step, "reason": str(error), "expected_action": expected,
                    "actual_url": getattr(getattr(self.actions, "page", None), "url", ""),
                }])
        return ReplayResult(success=True, executed_steps=executed)
