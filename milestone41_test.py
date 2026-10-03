"""Deterministic long-horizon, stuck, and recovery tests for Milestone 41."""

from pathlib import Path

from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from agent.task import TaskStatus
from browser.actions import BrowserActions
from browser.browser import Browser
from browser.reader import PageReader


TEST_DIR = Path(__file__).resolve().parent / "tests"


class NoLLM:
    def __init__(self): self.calls = 0
    def generate(self, prompt):
        self.calls += 1
        raise AssertionError("Deterministic selection should not call the LLM.")


class FailsOnceActions(BrowserActions):
    def __init__(self, page): super().__init__(page); self.failed = False
    def click(self, element_id):
        if not self.failed:
            self.failed = True
            self.page.locator("a").first.evaluate(
                "el => el.setAttribute('aria-label', 'Recovered Start')"
            )
            return {"success": False, "action": "click", "element_id": element_id,
                    "error_type": "ELEMENT_NOT_FOUND", "error": "Injected stale target."}
        return super().click(element_id)


class NeverCompleteEvaluator:
    def evaluate_goal(self, *args, **kwargs):
        return TaskStatus(status="continue", reason="Deliberately unchanged state.")


def make_loop(page, actions_class=BrowserActions, max_steps=10, **kwargs):
    browser = Browser(headless=True); browser.start(); browser.open(page.as_uri())
    planner = AgentPlanner(); planner.llm = NoLLM()
    loop = AgentLoop(PageReader(browser.page), planner, actions_class(browser.page), max_steps=max_steps,
                     max_retries_per_goal=3, deterministic_selection=True, **kwargs)
    return browser, planner, loop


def long_horizon_test():
    task = 'Click "Start", click "Continue", enter the customer reference, click "Review", click "Continue to Final".'
    browser, planner, loop = make_loop(TEST_DIR / "milestone41_a.html")
    try:
        assert loop.run(task) is True
        state = loop.last_execution_state
        assert state.completed_goal_ids == [1, 2, 3, 4, 5]
        assert state.deterministic_decisions == 5 and state.planner_calls == 0
        assert loop.last_memory.get_task_fact("customer_reference").value == "REF-4100"
        assert browser.page.title() == "M41 Final"
    finally: browser.close()


def recovery_replan_test():
    browser, _, loop = make_loop(TEST_DIR / "milestone41_a.html", FailsOnceActions)
    try:
        assert loop.run('Click "Start".') is True
        assert loop.last_execution_state.recovery_count >= 1
        assert browser.page.title() == "M41 B"
    finally: browser.close()


def stuck_detection_test():
    browser, _, loop = make_loop(TEST_DIR / "milestone41_stuck.html", max_steps=8,
                                 max_no_progress_cycles=2, max_identical_action_repetitions=2)
    loop.evaluator = NeverCompleteEvaluator()
    try:
        assert loop.run('Click "Tempting".') is False
        state = loop.last_execution_state
        assert state.failed_goal_ids == [1]
        assert state.total_steps <= 3
        assert state.no_progress_count >= 2 or state.repeated_action_count >= 2
    finally: browser.close()


def main():
    long_horizon_test(); print("[Test] Long-horizon five-goal execution: PASS")
    recovery_replan_test(); print("[Test] Recovery re-observe and replan: PASS")
    stuck_detection_test(); print("[Test] Bounded stuck-loop termination: PASS")
    print("MILESTONE 41 PASSED")


if __name__ == "__main__": main()
