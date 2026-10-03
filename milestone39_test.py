import json
from pathlib import Path

from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from browser.actions import BrowserActions
from browser.browser import Browser
from browser.reader import PageReader


BASE_DIR = Path(__file__).resolve().parent
TEST_DIR = BASE_DIR / "tests"


class DeterministicMemoryLLM:
    """Select the planner's highest-ranked current candidate."""

    def __init__(self):
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        start = prompt.index("VALID CURRENT ACTION CANDIDATES:")
        start += len("VALID CURRENT ACTION CANDIDATES:")
        end = prompt.index("\nRECENT COMPLETED ACTIONS:", start)
        candidate = json.loads(prompt[start:end].strip())[0]

        action = {"action": candidate["action"]}
        if candidate["action"] == "navigate":
            action["url"] = candidate["url"]
        else:
            action["element_id"] = candidate["element_id"]
            if candidate["action"] == "type":
                action["text"] = candidate["text"]
        return json.dumps(action)


def main():
    print("\n" + "=" * 60)
    print("MILESTONE 39 - GENERALIZED SEMANTIC FACTS E2E")
    print("=" * 60)

    page_a = TEST_DIR / "milestone39_a.html"
    assert page_a.exists(), "Milestone 39 Page A fixture is missing."
    task = (
        'Click "Continue to Page B", then click "Continue to Page C", '
        "and enter the customer reference."
    )
    browser = Browser(headless=True)
    browser.start()

    try:
        browser.open(page_a.as_uri())
        reader = PageReader(browser.page)
        actions = BrowserActions(browser.page)
        planner = AgentPlanner()
        deterministic_llm = DeterministicMemoryLLM()
        planner.llm = deterministic_llm
        loop = AgentLoop(
            reader=reader,
            planner=planner,
            actions=actions,
            max_steps=8,
            max_retries_per_goal=2,
        )

        result = loop.run(task)
        assert result is True
        memory = loop.last_memory
        assert memory is not None
        fact = memory.get_task_fact("customer_reference")
        assert fact is not None
        assert fact.value == "REF-9281"
        assert fact.key not in {"verification_code", "reference_number"}

        final_state = reader.read_page()
        assert final_state.title == "Tara M39 Page C"
        fields = [
            field for field in final_state.inputs
            if field.name == "customer_reference"
        ]
        assert fields and fields[0].value == "REF-9281"

        serialized_fact = json.dumps(fact.model_dump()).lower()
        for forbidden in ["selector", "element_id", "xpath", "dom_path"]:
            assert forbidden not in serialized_fact

        assert "REF-9281" in json.dumps(planner.last_memory_context)
        assert deterministic_llm.calls == 3

        print("[Test] Real AgentLoop result: PASS")
        print("[Test] New semantic fact discovered: True")
        print("[Test] Fact persisted across pages: True")
        print("[Test] Planner reused remembered fact: True")
        print("[Test] Final page correct: True")
        print("[Test] Correct value entered: True")
        print("[Test] DOM references stored in fact: False")
        print("\n" + "=" * 60)
        print("MILESTONE 39 PASSED")
        print("=" * 60)
    finally:
        browser.close()


if __name__ == "__main__":
    main()
