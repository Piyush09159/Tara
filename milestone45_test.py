"""Goal-graph validation plus an eight-goal deterministic AgentLoop run."""
from pathlib import Path
from agent.goals import Goal, GoalPlan, GoalDecomposer
from agent.memory import WorkingMemory
from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from browser.browser import Browser
from browser.reader import PageReader
from browser.actions import BrowserActions

class NoLLM:
    def generate(self, prompt): raise AssertionError("single current candidate expected")

def graph_tests():
    plan = GoalPlan(goals=[Goal(id=1, description="discover", goal_type="click"),
                           Goal(id=2, description="enter", goal_type="type_from_fact", fact_key="account_code", required_fact="account_code", prerequisites=[1])])
    plan.validate_graph(); memory = WorkingMemory()
    assert plan.current_goal(memory).id == 1
    plan.goals[0].completed = True
    assert plan.current_goal(memory) is None and plan.goals[1].status == "BLOCKED"
    memory.add_task_fact("account_code", "AC-1")
    assert plan.current_goal(memory).id == 2
    plan.add_goal(Goal(id=3, description="submit", goal_type="click", prerequisites=[2]))
    assert plan.goals[-1].dynamically_added
    for bad in [GoalPlan(goals=[Goal(id=1, description="a", goal_type="click"), Goal(id=1, description="b", goal_type="click")]),
                GoalPlan(goals=[Goal(id=1, description="a", goal_type="click", prerequisites=[2])]),
                GoalPlan(goals=[Goal(id=1, description="a", goal_type="click", prerequisites=[2]), Goal(id=2, description="b", goal_type="click", prerequisites=[1])])]:
        try: bad.validate_graph(); raise AssertionError("invalid graph accepted")
        except ValueError: pass

def integration_test():
    page = Path(__file__).parent / "tests" / "milestone43_form.html"
    browser = Browser(headless=True); browser.start()
    try:
        browser.open(page.as_uri()); planner = AgentPlanner(); planner.llm = NoLLM()
        loop = AgentLoop(PageReader(browser.page), planner, BrowserActions(browser.page, browser),
                         max_steps=12, deterministic_selection=True)
        task = ('Enter "Ada" as the first name, enter "Lovelace" as the last name, '
                'enter "ada@example.test" as the email, enter "secret" as the password, '
                'select "India", check "Terms and Conditions", choose "Premium", click "Submit".')
        assert loop.run(task)
        assert len(loop.last_execution_state.completed_goal_ids) == 8
    finally: browser.close()

if __name__ == "__main__":
    graph_tests(); print("[Graph] dependencies, blockers, insertion, validation, cycles: PASS")
    integration_test(); print("[Loop] eight semantic goals: PASS")
    print("MILESTONE 45 DETERMINISTIC PASSED")
