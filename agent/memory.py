from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agent.browser_memory import BrowserMemory
from agent.task_memory import TaskContextMemory
from agent.execution import TaskExecutionState


class WorkingMemory(BaseModel):
    """Working memory for the current task."""

    task: str = ""
    current_step: int = 0
    current_goal_id: Optional[int] = None

    observations: List[Dict[str, Any]] = Field(
        default_factory=list
    )

    completed_actions: List[Dict[str, Any]] = Field(
        default_factory=list
    )

    failed_actions: List[Dict[str, Any]] = Field(
        default_factory=list
    )

    recovery_events: List[Dict[str, Any]] = Field(
        default_factory=list
    )

    goal_history: List[Dict[str, Any]] = Field(
        default_factory=list
    )

    browser: BrowserMemory = Field(
        default_factory=BrowserMemory
    )

    task_context: TaskContextMemory = Field(
        default_factory=TaskContextMemory
    )

    execution: Optional[TaskExecutionState] = None

    # =========================================================
    # OBSERVATION MEMORY
    # =========================================================

    def add_observation(
        self,
        observation: Any,
    ):
        """
        Store the current observation and automatically extract
        semantic task facts from it.

        The current step comes from self.current_step, so callers
        only need to provide the observation.
        """

        if hasattr(
            observation,
            "model_dump",
        ):
            observation = observation.model_dump()

        if not isinstance(
            observation,
            dict,
        ):
            observation = {
                "value": observation
            }

        self.observations.append(
            observation
        )

        self.task_context.extract_from_observation(
            observation,
            step=self.current_step,
        )

        self.observations = (
            self.observations[-20:]
        )

    # =========================================================
    # BROWSER SNAPSHOT MEMORY
    # =========================================================

    def add_browser_snapshot(
        self,
        page_state: Any,
    ):
        """
        Store a semantic browser snapshot.

        IMPORTANT:
        BrowserMemory.record_snapshot() in Tara's existing
        Milestone 33 implementation uses the argument order:

            record_snapshot(step=..., page_state=...)

        Passing page_state positionally and step by keyword
        would bind 'page_state' to the first parameter and then
        assign 'step' twice, producing:

            TypeError:
            got multiple values for argument 'step'
        """

        self.browser.record_snapshot(
            step=self.current_step,
            page_state=page_state,
        )

    # =========================================================
    # BROWSER TRANSITION MEMORY
    # =========================================================

    def add_browser_transition(
        self,
        from_url: str,
        to_url: str,
        action: str,
        success: bool,
        navigated: bool,
    ):
        self.browser.record_transition(
            step=self.current_step,
            from_url=from_url,
            to_url=to_url,
            action=action,
            success=success,
            navigated=navigated,
        )

    # =========================================================
    # ACTION MEMORY
    # =========================================================

    def add_completed_action(
        self,
        action: Dict[str, Any],
    ):
        self.completed_actions.append(
            action
        )

        self.completed_actions = (
            self.completed_actions[-30:]
        )

    def add_failed_action(
        self,
        action: Dict[str, Any],
    ):
        self.failed_actions.append(
            action
        )

        self.failed_actions = (
            self.failed_actions[-30:]
        )

    # =========================================================
    # RECOVERY MEMORY
    # =========================================================

    def add_recovery_event(
        self,
        event: Dict[str, Any],
    ):
        self.recovery_events.append(
            event
        )

        self.recovery_events = (
            self.recovery_events[-20:]
        )

    # =========================================================
    # GOAL MEMORY
    # =========================================================

    def add_goal_event(
        self,
        event: Dict[str, Any],
    ):
        self.goal_history.append(
            event
        )

        self.goal_history = (
            self.goal_history[-20:]
        )

    # =========================================================
    # TASK FACT MEMORY
    # =========================================================

    def add_task_fact(
        self,
        key: str,
        value: str,
        source_url: str = "",
        source_step: Optional[int] = None,
        confidence: float = 1.0,
        evidence: str = "",
    ):
        if source_step is None:
            source_step = self.current_step

        return self.task_context.add_fact(
            key=key,
            value=value,
            source_url=source_url,
            source_step=source_step,
            confidence=confidence,
            evidence=evidence,
        )

    def get_task_fact(
        self,
        key: str,
    ):
        return self.task_context.get_fact(
            key
        )

    # =========================================================
    # RECENT MEMORY
    # =========================================================

    def recent_observation(
        self,
    ) -> Optional[Dict[str, Any]]:
        if not self.observations:
            return None

        return self.observations[-1]

    def recent_failure(
        self,
    ) -> Optional[Dict[str, Any]]:
        if not self.failed_actions:
            return None

        return self.failed_actions[-1]

    def recent_recovery(
        self,
    ) -> Optional[Dict[str, Any]]:
        if not self.recovery_events:
            return None

        return self.recovery_events[-1]

    def has_recent_action_signature(self, action: Dict[str, Any]) -> bool:
        """Check whether the most recent completed action is the same."""
        return bool(self.completed_actions and self.completed_actions[-1] == action)

    # =========================================================
    # PLANNER CONTEXT
    # =========================================================

    def planner_context(
        self,
    ) -> Dict[str, Any]:

        recent_observation = (
            self.recent_observation()
        )

        if isinstance(
            recent_observation,
            dict,
        ):
            recent_observation = dict(
                recent_observation
            )

            recent_observation[
                "task_context"
            ] = (
                self.task_context.planner_context()
            )

        browser_context = (
            self.browser.planner_context()
        )

        return {
            "task": self.task,

            "current_step": self.current_step,

            "current_goal_id": self.current_goal_id,

            "recent_actions": (
                self.completed_actions[-5:]
            ),

            "recent_failures": (
                self.failed_actions[-5:]
            ),

            "recent_recovery": (
                self.recovery_events[-5:]
            ),

            "goal_history": (
                self.goal_history[-5:]
            ),

            "recent_observation": (
                recent_observation
            ),

            "browser_state": (
                browser_context
            ),

            "task_context": (
                self.task_context.planner_context()
            ),
        }
