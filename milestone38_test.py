import inspect
import json
from pathlib import Path

from agent.loop import AgentLoop
from agent.planner import AgentPlanner
from browser.browser import Browser


BASE_DIR = Path(__file__).resolve().parent
TEST_DIR = BASE_DIR / "tests"


class DeterministicMemoryLLM:
    """
    Deterministic planner backend for Milestone 38.

    It returns the highest-confidence current candidate from
    Tara's own candidate list. This keeps the integration test
    deterministic while still exercising the real planner,
    memory, browser actions, verification, and agent loop.
    """

    def __init__(self):
        self.calls = 0

    def generate(self, prompt: str) -> str:

        self.calls += 1

        marker = "VALID CURRENT ACTION CANDIDATES:"
        start = prompt.find(marker)

        if start < 0:
            raise RuntimeError(
                "Planner prompt did not contain "
                "the candidate list."
            )

        start += len(marker)

        end_marker = "\nRECENT COMPLETED ACTIONS:"
        end = prompt.find(
            end_marker,
            start,
        )

        if end < 0:
            raise RuntimeError(
                "Planner prompt did not contain "
                "the expected candidate boundary."
            )

        candidate_text = prompt[
            start:end
        ].strip()

        candidates = json.loads(
            candidate_text
        )

        if not candidates:
            raise RuntimeError(
                "Planner produced no candidates."
            )

        candidate = candidates[0]

        action = {
            "action": candidate["action"]
        }

        if candidate["action"] == "navigate":
            action["url"] = candidate["url"]

        else:
            action["element_id"] = (
                candidate["element_id"]
            )

            if candidate["action"] == "type":
                action["text"] = candidate["text"]

        return json.dumps(action)


def write_pages():

    TEST_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    page_a = TEST_DIR / "context_e2e_a.html"
    page_b = TEST_DIR / "context_e2e_b.html"
    page_c = TEST_DIR / "context_e2e_c.html"

    page_a.write_text(
        """
<!DOCTYPE html>
<html>
<head>
    <title>Tara E2E Page A</title>
</head>
<body>
    <h1>Page A</h1>

    <p>
        Start of the multi-page task.
    </p>

    <a href="context_e2e_b.html">
        Go to Page B
    </a>
</body>
</html>
""",
        encoding="utf-8",
    )

    page_b.write_text(
        """
<!DOCTYPE html>
<html>
<head>
    <title>Tara E2E Page B</title>
</head>
<body>
    <h1>Page B</h1>

    <p>
        Important task information:
    </p>

    <p>
        Verification code: STAR-742
    </p>

    <a href="context_e2e_c.html">
        Continue to Page C
    </a>
</body>
</html>
""",
        encoding="utf-8",
    )

    page_c.write_text(
        """
<!DOCTYPE html>
<html>
<head>
    <title>Tara E2E Page C</title>
</head>
<body>
    <h1>Page C</h1>

    <form>
        <label for="verification_code">
            Verification Code
        </label>

        <input
            id="verification_code"
            name="verification_code"
            type="text"
            placeholder="Enter verification code"
        >
    </form>
</body>
</html>
""",
        encoding="utf-8",
    )

    return page_a


def find_class_with_method(
    module,
    method_name,
):
    for name, obj in vars(module).items():

        if not inspect.isclass(obj):
            continue

        if hasattr(obj, method_name):
            return obj

    raise RuntimeError(
        f"Could not locate a class exposing "
        f"{method_name} in {module.__name__}."
    )


def build_reader(browser, page):
    import browser.reader as reader_module

    reader_class = find_class_with_method(
        reader_module,
        "read_page",
    )

    attempts = [
        lambda: reader_class(page),
        lambda: reader_class(browser),
        lambda: reader_class(
            page=page
        ),
        lambda: reader_class(
            browser=browser
        ),
    ]

    errors = []

    for create in attempts:

        try:
            return create()
        except Exception as error:
            errors.append(
                str(error)
            )

    raise RuntimeError(
        "Could not instantiate the page reader.\n"
        + "\n".join(errors)
    )


def build_actions(browser, page):
    import browser.actions as actions_module

    actions_class = find_class_with_method(
        actions_module,
        "execute",
    )

    attempts = [
        lambda: actions_class(page),
        lambda: actions_class(browser),
        lambda: actions_class(
            page=page
        ),
        lambda: actions_class(
            browser=browser
        ),
    ]

    errors = []

    for create in attempts:

        try:
            return create()
        except Exception as error:
            errors.append(
                str(error)
            )

    raise RuntimeError(
        "Could not instantiate browser actions.\n"
        + "\n".join(errors)
    )


def verify_reader_contract(reader):
    page_state = reader.read_page()

    assert (
        page_state.title
        == "Tara E2E Page A"
    )

    assert any(
        link.text == "Go to Page B"
        for link in page_state.links
    )


def main():

    print("\n" + "=" * 60)
    print("MILESTONE 38 - FULL TASK-CONTEXT E2E")
    print("=" * 60)

    page_a = write_pages()

    task = (
        'Click "Go to Page B", then click '
        '"Continue to Page C", and enter '
        "the verification code."
    )

    browser = Browser(
        headless=True
    )

    browser.start()

    try:

        browser.open(
            page_a.as_uri()
        )

        reader = build_reader(
            browser,
            browser.page,
        )

        actions = build_actions(
            browser,
            browser.page,
        )

        verify_reader_contract(
            reader
        )

        planner = AgentPlanner()

        deterministic_llm = (
            DeterministicMemoryLLM()
        )

        planner.llm = (
            deterministic_llm
        )

        loop = AgentLoop(
            reader=reader,
            planner=planner,
            actions=actions,
            max_steps=8,
            max_retries_per_goal=2,
        )

        # -----------------------------------------------------
        # RUN THE REAL AGENT LOOP
        # -----------------------------------------------------

        result = loop.run(
            task
        )

        assert result is True, (
            "The real AgentLoop did not "
            "complete the task."
        )

        # -----------------------------------------------------
        # VERIFY WORKING MEMORY
        # -----------------------------------------------------

        memory = getattr(
            loop,
            "last_memory",
            None,
        )

        assert memory is not None, (
            "AgentLoop did not expose its "
            "working memory."
        )

        fact = memory.get_task_fact(
            "verification_code"
        )

        assert fact is not None, (
            "Verification code was not stored "
            "by the real agent loop."
        )

        assert fact.value == "STAR-742", (
            "Stored verification code is incorrect."
        )

        # -----------------------------------------------------
        # VERIFY FINAL BROWSER STATE
        # -----------------------------------------------------

        final_state = reader.read_page()

        assert (
            final_state.title
            == "Tara E2E Page C"
        ), (
            "Agent did not reach Page C."
        )

        code_inputs = [
            field
            for field in final_state.inputs
            if field.name
            == "verification_code"
        ]

        assert code_inputs, (
            "Verification code input was not found."
        )

        assert (
            code_inputs[0].value
            == "STAR-742"
        ), (
            "Verification code was not entered "
            "into the final form."
        )

        # -----------------------------------------------------
        # VERIFY MEMORY CONTENT
        # -----------------------------------------------------

        browser_context = (
            memory.browser.planner_context()
        )

        task_context = (
            memory.task_context.planner_context()
        )

        assert len(
            browser_context.get(
                "visited_urls",
                [],
            )
        ) >= 3

        assert (
            task_context["fact_count"]
            >= 1
        )

        # -----------------------------------------------------
        # VERIFY NO DOM REFERENCE IN THE FACT
        # -----------------------------------------------------

        fact_data = fact.model_dump()

        serialized = json.dumps(
            fact_data
        ).lower()

        for forbidden in [
            "selector",
            "element_id",
            "xpath",
            "dom_path",
        ]:
            assert forbidden not in serialized

        print(
            "\n[Test] Real AgentLoop result: PASS"
        )

        print(
            "[Test] Verification code discovered "
            "automatically: STAR-742"
        )

        print(
            "[Test] Fact persisted across pages: True"
        )

        print(
            "[Test] Planner reused remembered fact: True"
        )

        print(
            "[Test] Final page is Page C: True"
        )

        print(
            "[Test] Verification code entered: STAR-742"
        )

        print(
            "[Test] DOM references stored in fact: False"
        )

        print(
            "[Test] Planner calls:",
            deterministic_llm.calls,
        )

        print(
            "\n" + "=" * 60
        )
        print("✅ MILESTONE 38 PASSED")
        print("=" * 60)

    finally:
        browser.close()


if __name__ == "__main__":
    main()
