"""Real local Ollama/Qwen benchmark after a dynamic control becomes ready."""
from pathlib import Path
from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from browser.actions import BrowserActions
from browser.browser import Browser
from browser.reader import PageReader

if __name__ == "__main__":
    browser = Browser(headless=True); browser.start()
    try:
        browser.open((Path(__file__).parent / "tests" / "milestone44_delayed.html").as_uri())
        planner = AgentPlanner()
        actions = BrowserActions(browser.page, browser)
        loop = AgentLoop(PageReader(browser.page), planner, actions, max_steps=5)
        assert loop.run('Click "Continue".') is True
        assert browser.page.title() == "M44 Delayed Done"
        print({"model": planner.llm.model, "planner_calls": loop.last_execution_state.planner_calls,
               "deterministic_decisions": loop.last_execution_state.deterministic_decisions,
               "fallback_decisions": planner.diagnostics["fallback_selections"],
               "readiness_retries": actions.readiness.telemetry["readiness_attempts"],
               "stale_target_events": actions.runtime_telemetry["stale_target_events"],
               "reobservations": loop.last_memory.runtime_telemetry["reobservations"],
               "final_result": "PASS"})
        print("MILESTONE 44 REAL LLM PASSED")
    finally:
        browser.close()
