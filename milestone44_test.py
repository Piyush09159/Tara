"""Deterministic dynamic-runtime integration coverage for Milestone 44."""
from pathlib import Path
from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from browser.actions import BrowserActions
from browser.browser import Browser
from browser.reader import PageReader

TESTS = Path(__file__).resolve().parent / "tests"

class NoLLM:
    def generate(self, prompt):
        raise AssertionError("Each test supplies one current semantic candidate.")

class ReplaceOnceActions(BrowserActions):
    def __init__(self, page, browser=None): super().__init__(page, browser); self.replaced = False
    def click(self, element_id):
        if not self.replaced:
            self.replaced = True
            self.page.locator("#replace-me").evaluate(
                '''el => el.outerHTML = "<button id='replacement' aria-label='Replacement action' onclick=\\\"document.title='M44 Stale Done'\\\">Continue</button>"'''
            )
        return super().click(element_id)

class TransientActions(BrowserActions):
    def __init__(self, page, browser=None): super().__init__(page, browser); self.once = True
    def click(self, element_id):
        if self.once:
            self.once = False
            return {"success": False, "action": "click", "element_id": element_id,
                    "error_type": "ELEMENT_NOT_VISIBLE", "error": "Transient render."}
        return super().click(element_id)

def run(name, task, action_type=BrowserActions, steps=8):
    browser = Browser(headless=True); browser.start(); browser.open((TESTS / name).as_uri())
    planner = AgentPlanner(); planner.llm = NoLLM()
    actions = action_type(browser.page, browser)
    loop = AgentLoop(PageReader(browser.page), planner, actions, max_steps=steps,
                     max_retries_per_goal=3, deterministic_selection=True)
    return browser, actions, loop, loop.run(task)

def delayed_test():
    browser, actions, loop, ok = run("milestone44_delayed.html", 'Click "Continue".')
    try:
        assert ok and browser.page.title() == "M44 Delayed Done"
        assert actions.readiness.telemetry["readiness_attempts"] >= 1
    finally: browser.close()

def stale_test():
    browser, actions, loop, ok = run("milestone44_stale.html", 'Click "Continue".', ReplaceOnceActions)
    try:
        assert ok and browser.page.title() == "M44 Stale Done"
        assert any(item["error_type"] == "ELEMENT_NOT_FOUND" for item in loop.last_memory.failed_actions)
    finally: browser.close()

def spa_test():
    browser, actions, loop, ok = run("milestone44_spa.html", 'Click "Next", click "Finish".')
    try:
        assert ok and browser.page.title() == "M44 SPA Done"
        assert any(item.state_changed for item in loop.last_memory.browser.transitions)
    finally: browser.close()

def redirect_test():
    browser, actions, loop, ok = run("milestone44_redirect_start.html", 'Click "Continue".')
    try:
        assert ok and browser.page.title() == "M44 Redirect Done"
        assert browser.page.url.endswith("milestone44_redirect_end.html")
    finally: browser.close()

def popup_test():
    browser, actions, loop, ok = run("milestone44_popup.html", 'Click "Open Details", click "Finish".')
    try:
        assert ok and browser.page.title() == "M44 Popup Done"
        assert actions.runtime_telemetry["popup_detected"] >= 1
    finally: browser.close()

def transient_test():
    browser, actions, loop, ok = run("milestone44_stale.html", 'Click "Continue".', TransientActions)
    try:
        assert ok and len(loop.last_memory.recovery_events) >= 1
    finally: browser.close()

if __name__ == "__main__":
    delayed_test(); print("[A] delayed enable: PASS")
    stale_test(); print("[B] DOM replacement: PASS")
    spa_test(); print("[C] SPA same-URL: PASS")
    redirect_test(); print("[D] redirect: PASS")
    popup_test(); print("[E] popup tab: PASS")
    transient_test(); print("[F] transient readiness recovery: PASS")
    print("MILESTONE 44 DETERMINISTIC PASSED")
