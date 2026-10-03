"""Real Ollama/Qwen integration check; requires qwen2.5-coder:7b locally."""
from pathlib import Path
from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from browser.browser import Browser
from browser.reader import PageReader
from browser.actions import BrowserActions

if __name__ == "__main__":
    browser = Browser(headless=True); browser.start()
    try:
        browser.open((Path(__file__).parent / "tests" / "milestone42_form.html").as_uri())
        planner = AgentPlanner()
        loop = AgentLoop(PageReader(browser.page), planner, BrowserActions(browser.page), max_steps=4)
        assert loop.run('Enter the first name as "Ada".')
        print({"model": planner.llm.model, "diagnostics": planner.diagnostics})
        print("MILESTONE 42 REAL LLM PASSED")
    finally: browser.close()
