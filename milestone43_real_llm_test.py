"""Real Ollama/Qwen form benchmark using only local HTML and Playwright."""
from pathlib import Path

from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from browser.actions import BrowserActions
from browser.browser import Browser
from browser.reader import PageReader


if __name__ == "__main__":
    browser = Browser(headless=True); browser.start()
    try:
        browser.open((Path(__file__).parent / "tests" / "milestone43_form.html").as_uri())
        planner = AgentPlanner()
        loop = AgentLoop(PageReader(browser.page), planner, BrowserActions(browser.page), max_steps=10)
        task = ('Enter the first name as "Ada", enter the last name as "Lovelace", '
                'select "India", check "Terms and Conditions", choose "Premium", click "Submit".')
        assert loop.run(task) is True
        assert browser.page.locator("#country").input_value() == "India"
        assert browser.page.locator("#terms").is_checked()
        assert browser.page.locator("#premium").is_checked()
        print({"model": planner.llm.model, "diagnostics": planner.diagnostics,
               "selected_actions": loop.last_memory.completed_actions,
               "final_result": "PASS"})
        print("MILESTONE 43 REAL LLM PASSED")
    finally:
        browser.close()
