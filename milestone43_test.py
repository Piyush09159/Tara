"""Deterministic semantic-form and cross-page task integration tests."""
from pathlib import Path

from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from browser.actions import BrowserActions
from browser.browser import Browser
from browser.reader import PageReader

TEST_DIR = Path(__file__).resolve().parent / "tests"


class NoLLM:
    def generate(self, prompt):
        raise AssertionError("Each deterministic test has one current candidate.")


def run(page, task):
    browser = Browser(headless=True); browser.start(); browser.open(page.as_uri())
    planner = AgentPlanner(); planner.llm = NoLLM()
    loop = AgentLoop(PageReader(browser.page), planner, BrowserActions(browser.page),
                     max_steps=20, deterministic_selection=True)
    return browser, planner, loop, loop.run(task)


def multi_control_form_test():
    task = ('Enter "Ada" as the first name, enter "Lovelace" as the last name, '
            'enter "ada@example.test" as the email, enter "secret" as the password, '
            'select "India", check "Terms and Conditions", choose "Premium", click "Submit".')
    browser, planner, loop, success = run(TEST_DIR / "milestone43_form.html", task)
    try:
        assert success is True
        page = browser.page
        assert page.locator("#first").input_value() == "Ada"
        assert page.locator("#last").input_value() == "Lovelace"
        assert page.locator("#email").input_value() == "ada@example.test"
        assert page.locator("#password").input_value() == "secret"
        assert page.locator("#country").input_value() == "India"
        assert page.locator("#terms").is_checked()
        assert page.locator("#premium").is_checked()
        assert page.title() == "M43 Submitted"
        state = PageReader(page).read_page()
        assert next(field for field in state.inputs if field.name == "country").selected == "India"
        assert next(field for field in state.inputs if field.name == "terms").checked is True
        assert planner.diagnostics["candidate_count_after_filter"] >= 1
    finally:
        browser.close()


def cross_page_fact_form_test():
    task = ('Click "Continue", enter the customer reference, '
            'enter "customer@example.test" as the email, select "India", '
            'check "Terms", click "Submit".')
    browser, _, loop, success = run(TEST_DIR / "milestone43_facts.html", task)
    try:
        assert success is True
        assert loop.last_memory.get_task_fact("customer_reference").value == "REF-9281"
        assert browser.page.locator("#reference").input_value() == "REF-9281"
        assert browser.page.locator("#fact-country").input_value() == "India"
        assert browser.page.locator("#fact-terms").is_checked()
        assert browser.page.title() == "M43 Fact Submitted"
    finally:
        browser.close()


def main():
    multi_control_form_test(); print("[Test] Multi-control semantic form: PASS")
    cross_page_fact_form_test(); print("[Test] Cross-page fact form: PASS")
    print("MILESTONE 43 DETERMINISTIC PASSED")


if __name__ == "__main__":
    main()
