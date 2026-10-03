"""Bounded runtime state for a single AgentLoop run."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ActionProgress(BaseModel):
    meaningful: bool = False
    signals: List[str] = Field(default_factory=list)


class TaskExecutionState(BaseModel):
    task: str
    current_goal_id: Optional[int] = None
    goal_statuses: Dict[int, str] = Field(default_factory=dict)
    completed_goal_ids: List[int] = Field(default_factory=list)
    failed_goal_ids: List[int] = Field(default_factory=list)
    current_attempt: int = 0
    total_steps: int = 0
    recovery_count: int = 0
    no_progress_count: int = 0
    repeated_action_count: int = 0
    planner_calls: int = 0
    deterministic_decisions: int = 0
    recovery_replans: int = 0
    last_action: Optional[dict] = None
    last_result: Optional[dict] = None
    last_url: str = ""
    last_fingerprint: str = ""

    def activate_goal(self, goal_id: int):
        self.current_goal_id = goal_id
        self.goal_statuses.setdefault(goal_id, "pending")
        self.goal_statuses[goal_id] = "active"

    def complete_goal(self, goal_id: int):
        self.goal_statuses[goal_id] = "completed"
        if goal_id not in self.completed_goal_ids:
            self.completed_goal_ids.append(goal_id)

    def fail_goal(self, goal_id: int):
        self.goal_statuses[goal_id] = "failed"
        if goal_id not in self.failed_goal_ids:
            self.failed_goal_ids.append(goal_id)

    def record_action(self, action: dict, result: dict):
        if self.last_action == action:
            self.repeated_action_count += 1
        else:
            self.repeated_action_count = 1
        self.last_action = action
        self.last_result = result
        self.current_attempt += 1

    def record_progress(self, progress: ActionProgress):
        if progress.meaningful:
            self.no_progress_count = 0
        else:
            self.no_progress_count += 1

    def diagnostics(self):
        return self.model_dump()
