"""Versioned, atomic JSON checkpoints for resumable Tara tasks."""
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field

from agent.goals import GoalPlan
from agent.memory import WorkingMemory
from agent.execution import TaskExecutionState


class TaskCheckpoint(BaseModel):
    checkpoint_version: int = 1
    checkpoint_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    task: str
    goal_plan: GoalPlan
    working_memory: WorkingMemory
    execution_state: TaskExecutionState
    current_url: str = ""
    active_page_identity: str = ""
    checkpoint_reason: str = "manual"

    def validate_checkpoint(self):
        if self.checkpoint_version != 1:
            raise ValueError("Unsupported checkpoint version.")
        self.goal_plan.validate_graph()
        # Task facts are semantic; reject accidental browser reference keys.
        forbidden = {"selector", "element_id", "xpath", "locator"}
        for fact in self.working_memory.task_context.facts:
            if forbidden.intersection(fact.model_dump().keys()):
                raise ValueError("Task facts must not contain browser references.")
        return True


class CheckpointManager:
    def __init__(self, directory=".tara/checkpoints"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, checkpoint_id):
        return self.directory / f"{checkpoint_id}.json"

    def save(self, checkpoint: TaskCheckpoint):
        checkpoint.validate_checkpoint()
        path = self._path(checkpoint.checkpoint_id)
        fd, temporary = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(checkpoint.model_dump(mode="json"), handle, indent=2)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        return checkpoint.checkpoint_id

    def load(self, checkpoint_id):
        path = self._path(checkpoint_id)
        if not path.exists(): raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")
        try:
            with path.open(encoding="utf-8") as handle: raw = json.load(handle)
            checkpoint = TaskCheckpoint.model_validate(raw); checkpoint.validate_checkpoint()
            return checkpoint
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"Invalid checkpoint '{checkpoint_id}': {error}") from error

    def list(self):
        return sorted(path.stem for path in self.directory.glob("*.json"))

    def delete(self, checkpoint_id):
        self._path(checkpoint_id).unlink()
