"""Checkpoint persistence, corruption safety, and fresh-session resume tests."""
import json
import tempfile
from pathlib import Path
from agent.checkpoint import CheckpointManager, TaskCheckpoint
from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from browser.browser import Browser
from browser.reader import PageReader
from browser.actions import BrowserActions

TESTS = Path(__file__).parent / "tests"
class NoLLM:
    def generate(self, prompt):
        import re, json
        candidates = json.loads(re.search(r"VALID CURRENT ACTION CANDIDATES:\s*(\[.*?\])\s*\n\nRECENT", prompt, re.S).group(1))
        choice = candidates[0]; return json.dumps({key: choice[key] for key in ("action", "element_id", "text", "url", "option") if key in choice})

class StopAfterTwo(BrowserActions):
    def __init__(self, page, browser=None): super().__init__(page, browser); self.count=0
    def execute(self, action):
        self.count += 1
        if self.count > 2: return {"success": False, "action": action.action, "error_type":"ELEMENT_NOT_FOUND", "error":"simulated session loss"}
        return super().execute(action)

def loop(browser, actions_cls=BrowserActions):
    planner=AgentPlanner(); planner.llm=NoLLM(); actions=actions_cls(browser.page, browser)
    return AgentLoop(PageReader(browser.page), planner, actions, max_steps=8, max_retries_per_goal=1)

def corruption_tests(directory):
    manager=CheckpointManager(directory)
    for identifier, content in [("broken", "{"), ("wrong", json.dumps({"checkpoint_version":99}))]:
        (Path(directory)/f"{identifier}.json").write_text(content, encoding="utf-8")
        try: manager.load(identifier); raise AssertionError("corrupt checkpoint accepted")
        except (ValueError, FileNotFoundError): pass
    try: manager.load("missing"); raise AssertionError("missing checkpoint accepted")
    except FileNotFoundError: pass

def resume_test(directory):
    task='Click "Go to Page B", click "Continue to Page C", enter the verification code.'
    first=Browser(headless=True); first.start(); first.open((TESTS/"context_e2e_a.html").as_uri())
    try:
        interrupted=loop(first, StopAfterTwo); interrupted.checkpoints=CheckpointManager(directory)
        assert interrupted.run(task) is False
        checkpoint_id=interrupted.create_checkpoint("session_loss")
        assert interrupted.last_memory.get_task_fact("verification_code").value == "STAR-742"
        assert interrupted.last_goal_plan.goals[0].completed and interrupted.last_goal_plan.goals[1].completed
    finally: first.close()
    second=Browser(headless=True); second.start(); second.open((TESTS/"context_e2e_c.html").as_uri())
    try:
        resumed=loop(second); resumed.checkpoints=CheckpointManager(directory)
        assert resumed.resume_from_checkpoint(checkpoint_id)
        assert second.page.locator("input").input_value() == "STAR-742"
        assert resumed.last_goal_plan.goals[0].completed and resumed.last_goal_plan.goals[1].completed
        assert len(resumed.last_memory.completed_actions) == 3
    finally: second.close()

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        corruption_tests(directory); print("[Checkpoint] corruption/missing/version rejection: PASS")
        resume_test(directory); print("[Resume] facts, completed goals, re-observation, current target resolution: PASS")
    print("MILESTONE 46 DETERMINISTIC PASSED")
