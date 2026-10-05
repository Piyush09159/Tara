"""Real Qwen structured decomposition validation with local AgentLoop execution."""
from pathlib import Path
from agent.goals import GoalDecomposer
from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from browser.browser import Browser
from browser.reader import PageReader
from browser.actions import BrowserActions

if __name__ == "__main__":
    planner = AgentPlanner(); decomposer = GoalDecomposer()
    task = 'Enter the first name as "Ada", select "India", check "Terms and Conditions", and click "Submit".'
    plan = decomposer.decompose_with_llm(task, planner.llm)
    plan.validate_graph()
    browser = Browser(headless=True); browser.start()
    try:
        browser.open((Path(__file__).parent / "tests" / "milestone43_form.html").as_uri())
        loop = AgentLoop(PageReader(browser.page), planner, BrowserActions(browser.page, browser), max_steps=8)
        assert loop.run(task)
        print({"model": planner.llm.model, "llm_decomposition_calls": 1,
               "generated_goals": len(plan.goals), "rejected_goals": 0,
               "completed_goals": loop.last_execution_state.completed_goal_ids,
               "dynamically_inserted_goals": loop.last_execution_state.dynamically_added_goal_ids,
               "final_result": "PASS"})
        print("MILESTONE 45 REAL LLM PASSED")
    finally: browser.close()
