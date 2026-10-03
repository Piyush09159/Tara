from pathlib import Path
import json

from playwright.sync_api import sync_playwright

from agent.memory import WorkingMemory
from agent.planner import AgentPlanner


BASE_DIR = Path(__file__).resolve().parent
TEST_DIR = BASE_DIR / "tests"


def write_test_pages():

    TEST_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    page_a = TEST_DIR / "task_context_page_a.html"
    page_b = TEST_DIR / "task_context_page_b.html"
    page_c = TEST_DIR / "task_context_page_c.html"

    page_a.write_text(
        """
<!DOCTYPE html>
<html>
<head>
    <title>Tara Task Context - Page A</title>
</head>
<body>
    <h1>Page A</h1>

    <p>
        This page starts the task.
    </p>

    <a href="task_context_page_b.html">
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
    <title>Tara Task Context - Page B</title>
</head>
<body>

    <h1>Page B</h1>

    <p>
        Important information discovered on this page.
    </p>

    <p>
        Verification code: STAR-742
    </p>

    <a href="task_context_page_c.html">
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
    <title>Tara Task Context - Page C</title>
</head>
<body>

    <h1>Page C</h1>

    <label for="verification_code">
        Verification Code
    </label>

    <input
        id="verification_code"
        name="verification_code"
        type="text"
        placeholder="Enter verification code"
    />

</body>
</html>
""",
        encoding="utf-8",
    )

    return page_a


def observe_page(page):

    return {
        "url": page.url,
        "title": page.title(),
        "text": page.locator("body").inner_text(),
    }


def assert_no_dom_references(facts):

    serialized = json.dumps(
        facts,
        ensure_ascii=False,
    ).lower()

    forbidden = [
        "selector",
        "element_id",
        "dom_path",
        "xpath",
    ]

    for value in forbidden:

        assert value not in serialized, (
            f"Task facts unexpectedly contain "
            f"browser reference: {value}"
        )


def main():

    page_a = write_test_pages()

    task = (
        "Go to Page B, remember the verification code, "
        "then go to Page C and enter the verification code."
    )

    memory = WorkingMemory(
        task=task
    )

    print("\n" + "=" * 60)
    print("MILESTONE 36 - TASK CONTEXT MEMORY")
    print("=" * 60)

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        # =====================================================
        # STEP 1 - PAGE A
        # =====================================================

        memory.current_step = 1

        page.goto(
            page_a.as_uri(),
            wait_until="domcontentloaded",
        )

        memory.add_observation(
            observe_page(page)
        )

        print(
            "\n[Step 1]"
            f" {page.title()}"
        )

        # =====================================================
        # STEP 2 - PAGE B
        # =====================================================

        page.get_by_role(
            "link",
            name="Go to Page B",
        ).click()

        page.wait_for_load_state(
            "domcontentloaded"
        )

        memory.current_step = 2

        page_b_observation = observe_page(
            page
        )

        memory.add_observation(
            page_b_observation
        )

        print(
            "\n[Step 2]"
            f" {page.title()}"
        )

        # =====================================================
        # FACT EXTRACTION
        # =====================================================

        fact = memory.get_task_fact(
            "verification_code"
        )

        assert fact is not None, (
            "Verification code was not discovered."
        )

        assert fact.value == "STAR-742", (
            "Incorrect verification code extracted."
        )

        print(
            "[Memory] Discovered fact:"
            f" verification_code={fact.value}"
        )

        print(
            "[Memory] Source URL:"
            f" {fact.source_url}"
        )

        print(
            "[Memory] Source step:"
            f" {fact.source_step}"
        )

        # =====================================================
        # VERIFY FACT IS SEMANTIC ONLY
        # =====================================================

        assert_no_dom_references(
            [
                item.model_dump()
                for item in memory.task_context.facts
            ]
        )

        print(
            "[Memory] No DOM selectors or element IDs "
            "stored in task facts."
        )

        # =====================================================
        # STEP 3 - PAGE C
        # =====================================================

        page.get_by_role(
            "link",
            name="Continue to Page C",
        ).click()

        page.wait_for_load_state(
            "domcontentloaded"
        )

        memory.current_step = 3

        memory.add_observation(
            observe_page(page)
        )

        print(
            "\n[Step 3]"
            f" {page.title()}"
        )

        # =====================================================
        # FACT PERSISTENCE ACROSS PAGE TRANSITION
        # =====================================================

        fact_after_navigation = (
            memory.get_task_fact(
                "verification_code"
            )
        )

        assert (
            fact_after_navigation is not None
        ), (
            "Fact disappeared after navigation."
        )

        assert (
            fact_after_navigation.value
            == "STAR-742"
        ), (
            "Fact value changed after navigation."
        )

        print(
            "[Memory] Fact persisted across page transition:"
            f" {fact_after_navigation.value}"
        )

        # =====================================================
        # PLANNER CONTEXT
        # =====================================================

        planner = AgentPlanner()

        planner_context = (
            planner.build_memory_context(
                memory
            )
        )

        planner_text = json.dumps(
            planner_context,
            ensure_ascii=False,
            default=str,
        )

        assert "verification_code" in (
            planner_text
        ), (
            "Planner context does not contain "
            "verification_code."
        )

        assert "STAR-742" in (
            planner_text
        ), (
            "Planner context does not contain "
            "STAR-742."
        )

        print(
            "[Planner] Previous-page fact is "
            "available in planner context."
        )

        # =====================================================
        # REUSE FACT ON PAGE C
        # =====================================================

        input_box = page.get_by_label(
            "Verification Code"
        )

        input_box.fill(
            fact_after_navigation.value
        )

        actual_value = input_box.input_value()

        assert actual_value == "STAR-742", (
            "Stored task fact was not reused correctly."
        )

        print(
            "[Action] Entered stored verification code:"
            f" {actual_value}"
        )

        # =====================================================
        # FINAL MEMORY SUMMARY
        # =====================================================

        print(
            "\n[Summary]"
        )

        print(
            "  Task facts:",
            len(memory.task_context.facts),
        )

        print(
            "  Verification code:",
            fact_after_navigation.value,
        )

        print(
            "  Current page:",
            page.title(),
        )

        browser.close()

    print("\n" + "=" * 60)
    print("✅ MILESTONE 36 PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()