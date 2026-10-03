"""Milestone 40 integration and deterministic recovery regression tests."""

import json
from pathlib import Path

from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from agent.semantic import normalize_semantic_key, semantic_keys_match
from browser.actions import BrowserActions
from browser.browser import Browser
from browser.identity import stable_element_ids
from browser.reader import PageReader


TEST_DIR = Path(__file__).resolve().parent / "tests"


def candidate_from_prompt(prompt):
    start = prompt.index("VALID CURRENT ACTION CANDIDATES:")
    start += len("VALID CURRENT ACTION CANDIDATES:")
    end = prompt.index("\nRECENT COMPLETED ACTIONS:", start)
    return json.loads(prompt[start:end].strip())[0]


def action_from_candidate(candidate):
    action = {"action": candidate["action"]}
    if candidate["action"] == "navigate":
        action["url"] = candidate["url"]
    else:
        action["element_id"] = candidate["element_id"]
        if candidate["action"] == "type":
            action["text"] = candidate["text"]
    return action


class CurrentCandidateLLM:
    def generate(self, prompt):
        return json.dumps(action_from_candidate(candidate_from_prompt(prompt)))


class StaleTargetLLM(CurrentCandidateLLM):
    """Once Page C is reached, deliberately return an old Page A target."""

    def __init__(self):
        self.stale_id = None
        self.supplied_stale_target = False

    def generate(self, prompt):
        candidate = candidate_from_prompt(prompt)
        if candidate["action"] == "click" and self.stale_id is None:
            self.stale_id = candidate["element_id"]
        if candidate["action"] == "type" and not self.supplied_stale_target:
            self.supplied_stale_target = True
            return json.dumps({"action": "type", "element_id": self.stale_id, "text": candidate["text"]})
        return json.dumps(action_from_candidate(candidate))


class InvisibleOnceActions(BrowserActions):
    def __init__(self, page):
        super().__init__(page)
        self.failed_once = False

    def click(self, element_id):
        if not self.failed_once:
            self.failed_once = True
            return {
                "success": False, "action": "click", "element_id": element_id,
                "error_type": "ELEMENT_NOT_VISIBLE", "error": "Injected transient visibility failure.",
            }
        return super().click(element_id)


class DisabledOnceActions(BrowserActions):
    def __init__(self, page):
        super().__init__(page)
        self.failed_once = False

    def type(self, element_id, text):
        if not self.failed_once:
            self.failed_once = True
            # Model a disabled control becoming usable after the recovery
            # cycle. Its changed current-page semantics yield a new target,
            # so the blacklisted old action cannot be blindly reused.
            self.page.locator("#customer_reference").evaluate(
                "el => { el.disabled = false; el.placeholder = 'Customer Reference ready'; }"
            )
            return {
                "success": False, "action": "type", "element_id": element_id, "text": text,
                "error_type": "ELEMENT_DISABLED", "error": "Injected disabled field; it becomes enabled on re-observe.",
            }
        return super().type(element_id, text)


class NavigationFailsOnceActions(BrowserActions):
    def __init__(self, page):
        super().__init__(page)
        self.failed_once = False

    def navigate(self, url):
        if not self.failed_once:
            self.failed_once = True
            return {
                "success": False, "action": "navigate", "url": url,
                "error_type": "NAVIGATION_ERROR", "error": "Injected transient navigation failure.",
            }
        return super().navigate(url)


def run_loop(page_path, task, actions_class=BrowserActions, llm=None, max_steps=8):
    browser = Browser(headless=True)
    browser.start()
    browser.open(page_path.as_uri())
    reader = PageReader(browser.page)
    actions = actions_class(browser.page)
    planner = AgentPlanner()
    planner.llm = llm or CurrentCandidateLLM()
    loop = AgentLoop(reader, planner, actions, max_steps=max_steps, max_retries_per_goal=3)
    return browser, reader, actions, planner, loop


def test_shared_identity_and_normalization():
    values = ["Customer Reference", "customer reference", "customer_reference", "Customer-Reference", "  CUSTOMER   REFERENCE  "]
    assert {normalize_semantic_key(value) for value in values} == {"customer_reference"}
    assert semantic_keys_match("customer_reference", "Customer Reference")

    browser, reader, actions, _, _ = run_loop(TEST_DIR / "milestone40_c.html", "Click \"Duplicate\".")
    try:
        state = reader.read_page()
        duplicates = [button.id for button in state.buttons if button.text == "Duplicate"]
        assert len(duplicates) == 2 and duplicates[0] != duplicates[1]
        locator = actions.page.locator(
            "button, input[type='button'], input[type='submit'], input[type='reset']"
        )
        current_buttons = [locator.nth(index) for index in range(locator.count())]
        assert stable_element_ids("button", current_buttons) == [
            button.id for button in state.buttons
        ]
        for element_id in duplicates:
            resolved = actions._find_by_id(element_id)
            assert resolved.inner_text().strip() == "Duplicate"
    finally:
        browser.close()


def test_disabled_recovery():
    browser, reader, _, _, loop = run_loop(
        TEST_DIR / "milestone40_c.html",
        'Enter "REF-0001".',
        actions_class=DisabledOnceActions,
    )
    try:
        assert loop.run('Enter "REF-0001".') is True
        assert any(event["error_type"] == "ELEMENT_DISABLED" for event in loop.last_memory.recovery_events)
        assert reader.read_page().inputs[0].value == "REF-0001"
    finally:
        browser.close()


def test_navigation_retry():
    page_b = TEST_DIR / "milestone40_b.html"
    browser, _, _, _, loop = run_loop(
        TEST_DIR / "milestone40_a.html",
        f"Navigate to {page_b.as_uri()}",
        actions_class=NavigationFailsOnceActions,
    )
    try:
        assert loop.run(f"Navigate to {page_b.as_uri()}") is True
        assert any(event["strategy"] == "retry_navigation" for event in loop.last_memory.recovery_events)
        assert browser.page.url == page_b.as_uri()
    finally:
        browser.close()


def test_semantic_stale_target_recovery():
    task = 'Click "Continue to Page B", then click "Continue to Page C", and enter the customer reference.'
    stale_llm = StaleTargetLLM()
    browser, reader, actions, planner, loop = run_loop(
        TEST_DIR / "milestone40_a.html", task, InvisibleOnceActions, stale_llm, max_steps=8,
    )
    try:
        assert loop.run(task) is True
        fact = loop.last_memory.get_task_fact("customer_reference")
        assert fact and fact.value == "REF-9281"
        assert stale_llm.supplied_stale_target
        assert any(event["error_type"] == "ELEMENT_NOT_VISIBLE" for event in loop.last_memory.recovery_events)
        assert planner.diagnostics["invalid_llm_decisions"] == 1
        assert planner.diagnostics["fallback_selections"] == 1
        assert reader.read_page().inputs[0].value == "REF-9281"
        assert "REF-9281" in json.dumps(planner.last_memory_context)
        planner_browser_context = planner.last_memory_context["browser_state"]
        assert len(planner_browser_context["recent_page_history"]) <= 3
        assert len(planner_browser_context["visited_urls"]) <= 8
        assert len(planner_browser_context["recent_transitions"]) <= 5
        assert actions.failed_once
    finally:
        browser.close()


def main():
    print("\n" + "=" * 60)
    print("MILESTONE 40 - UNIFIED TARGET RESOLUTION AND RECOVERY")
    print("=" * 60)
    test_shared_identity_and_normalization()
    print("[Test A] Shared IDs, duplicate siblings, and normalization: PASS")
    test_disabled_recovery()
    print("[Test B] Disabled target recovery and replan: PASS")
    test_navigation_retry()
    print("[Test C] Navigation retry policy consumed: PASS")
    test_semantic_stale_target_recovery()
    print("[Test D] Stale target rejected; current semantic target resolved: PASS")
    print("\nMILESTONE 40 PASSED")


if __name__ == "__main__":
    main()
