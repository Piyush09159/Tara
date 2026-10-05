"""Real Qwen checkpoint/resume benchmark using local cross-page fixtures."""
import tempfile
from pathlib import Path
from agent.checkpoint import CheckpointManager
from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from browser.browser import Browser
from browser.reader import PageReader
from browser.actions import BrowserActions

class StopAfterTwo(BrowserActions):
    def __init__(self, page, browser=None): super().__init__(page, browser); self.count=0
    def execute(self, action):
        self.count += 1
        if self.count > 2: return {"success":False,"action":action.action,"error_type":"ELEMENT_NOT_FOUND","error":"session restart"}
        return super().execute(action)

if __name__ == "__main__":
    task='Click "Go to Page B", click "Continue to Page C", enter the verification code.'
    fixture=Path(__file__).parent/"tests"
    with tempfile.TemporaryDirectory() as directory:
        first=Browser(headless=True); first.start(); first.open((fixture/"context_e2e_a.html").as_uri())
        try:
            before=AgentPlanner(); initial=AgentLoop(PageReader(first.page), before, StopAfterTwo(first.page, first), max_steps=8, max_retries_per_goal=1)
            initial.checkpoints=CheckpointManager(directory); assert initial.run(task) is False
            checkpoint_id=initial.create_checkpoint("real_session_restart")
            before_calls=before.diagnostics["llm_calls"]
        finally: first.close()
        second=Browser(headless=True); second.start(); second.open((fixture/"context_e2e_c.html").as_uri())
        try:
            after=AgentPlanner(); resumed=AgentLoop(PageReader(second.page), after, BrowserActions(second.page, second), max_steps=5)
            resumed.checkpoints=CheckpointManager(directory); assert resumed.resume_from_checkpoint(checkpoint_id)
            print({"model":after.llm.model,"planner_calls_before_checkpoint":before_calls,
                   "planner_calls_after_resume":after.diagnostics["llm_calls"],
                   "deterministic_decisions":resumed.last_execution_state.deterministic_decisions,
                   "fallback_decisions":after.diagnostics["fallback_selections"],
                   "recovered_facts":len(resumed.last_memory.task_context.facts),
                   "restored_goal_count":len(resumed.last_goal_plan.goals),
                   "completed_goal_count":len(resumed.last_execution_state.completed_goal_ids),"final_result":"PASS"})
            print("MILESTONE 46 REAL LLM PASSED")
        finally: second.close()
