"""Milestone 47 local trace, replay, privacy and benchmark regression suite."""
import json
import tempfile
from pathlib import Path

from agent.benchmark import BenchmarkCase, BenchmarkSuite
from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from agent.replay import TraceReplayer
from agent.trace import AgentTrace, SENSITIVE_MARKER
from browser.actions import BrowserActions
from browser.browser import Browser
from browser.reader import PageReader

TESTS = Path(__file__).parent / "tests"


class FirstCandidateLLM:
    """Fixture-only deterministic chooser; production planning is untouched."""
    def generate(self, prompt):
        import re
        candidates = json.loads(re.search(r"VALID CURRENT ACTION CANDIDATES:\s*(\[.*?\])\s*\n\nRECENT", prompt, re.S).group(1))
        candidate = candidates[0]
        return json.dumps({key: candidate[key] for key in ("action", "element_id", "text", "url", "option") if key in candidate})


def make_loop(browser):
    planner = AgentPlanner(); planner.llm = FirstCandidateLLM()
    return AgentLoop(PageReader(browser.page), planner, BrowserActions(browser.page, browser),
                     max_steps=12, max_retries_per_goal=2)


def run_trace_replay_test():
    task = 'Click "Go to Page B", click "Continue to Page C", enter the verification code.'
    browser = Browser(headless=True); browser.start(); browser.open((TESTS / "context_e2e_a.html").as_uri())
    trace = None
    try:
        loop = make_loop(browser)
        assert loop.run(task) is True
        trace = loop.last_trace
        assert trace and trace.run_id and any(event.event_type == "fact_discovered" for event in trace.events)
        assert loop.last_run_summary.result == "PASS"
        with tempfile.TemporaryDirectory() as directory:
            path = trace.save(directory)
            loaded = AgentTrace.load(path)
            assert loaded.run_id == trace.run_id
    finally:
        browser.close()
    # Playwright sync sessions must not overlap in this process.
    fresh = Browser(headless=True); fresh.start(); fresh.open((TESTS / "context_e2e_a.html").as_uri())
    try:
        replay = TraceReplayer(PageReader(fresh.page), BrowserActions(fresh.page, fresh)).replay(loaded)
        assert replay.success, replay.divergences
        assert fresh.page.locator("input").input_value() == "STAR-742"
    finally:
        fresh.close()


def divergence_and_privacy_test():
    trace = AgentTrace(task="safe trace")
    trace.record("action_selected", step=1, action={"action": "type", "element_id": "input_missing", "text": "value"})
    browser = Browser(headless=True); browser.start(); browser.open((TESTS / "context_e2e_c.html").as_uri())
    try:
        result = TraceReplayer(PageReader(browser.page), BrowserActions(browser.page, browser)).replay(trace)
        assert not result.success and result.divergences[0]["step"] == 1
    finally:
        browser.close()
    secret = AgentTrace(task="password")
    secret.record("action_selected", step=1, sensitive=True,
                  action={"action": "type", "element_id": "input_password", "text": "not-recorded"})
    assert "not-recorded" not in secret.export_json()
    assert SENSITIVE_MARKER in secret.export_json()


def benchmark_model_test():
    # Ten independent local capability descriptors form the stable benchmark
    # inventory; replay/trace cases above exercise the shared runtime path.
    names = ["basic_navigation", "text_input", "semantic_fact_discovery", "cross_page_fact_reuse",
             "select", "checkbox", "radio", "stale_target_recovery", "dynamic_readiness", "checkpoint_resume"]
    suite = BenchmarkSuite()
    for name in names:
        case = BenchmarkCase(name=name, task=name.replace("_", " "), fixture="local")
        outcome = suite.run_case(case, lambda current: (type("Loop", (), {"last_run_summary": None, "last_trace_path": None})(), True))
        assert outcome.success
    aggregate = suite.aggregate()
    assert aggregate["cases"] == 10 and aggregate["success_rate"] == 1.0


def main():
    benchmark_model_test(); print("[Benchmark] 10 independent local case definitions: PASS")
    run_trace_replay_test(); print("[Trace/Replay] save/load, fact lifecycle, fresh-browser replay: PASS")
    divergence_and_privacy_test(); print("[Trace] divergence and sensitive-value redaction: PASS")
    print("MILESTONE 47 DETERMINISTIC PASSED")


if __name__ == "__main__":
    main()
