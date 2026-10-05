"""Small real-Qwen local benchmark; no external sites are used."""
from pathlib import Path
from time import perf_counter

from agent.benchmark import BenchmarkCase, BenchmarkSuite
from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from browser.actions import BrowserActions
from browser.browser import Browser
from browser.reader import PageReader

TESTS = Path(__file__).parent / "tests"


def run_case(case):
    browser = Browser(headless=True); browser.start(); browser.open((TESTS / case.fixture).as_uri())
    try:
        planner = AgentPlanner()
        loop = AgentLoop(PageReader(browser.page), planner, BrowserActions(browser.page, browser), max_steps=12)
        return loop, loop.run(case.task)
    finally:
        browser.close()


def main():
    cases = [BenchmarkCase(name="real_cross_page_fact", fixture="context_e2e_a.html",
                            task='Click "Go to Page B", click "Continue to Page C", enter the verification code.')]
    suite = BenchmarkSuite()
    for case in cases:
        result = suite.run_case(case, run_case)
        print(f"[Real benchmark] {case.name}: {'PASS' if result.success else 'FAIL'}")
    aggregate = suite.aggregate()
    print("[Real benchmark] aggregate:", aggregate)
    if aggregate["successes"] != len(cases):
        raise SystemExit("MILESTONE 47 REAL LLM FAILED")
    print("MILESTONE 47 REAL LLM PASSED")


if __name__ == "__main__":
    main()
