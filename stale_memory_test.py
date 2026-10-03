from pathlib import Path

from browser.browser import Browser
from browser.reader import PageReader
from browser.actions import BrowserActions
from agent.planner import AgentPlanner
from agent.loop import AgentLoop


class FakeLLM:

    def __init__(self):

        self.responses = [
            # -------------------------------------------------
            # STEP 1
            # Valid current Page 1 action.
            # -------------------------------------------------
            {
                "action": "click",
                "element_id": "link_47396bc29f",
            },

            # -------------------------------------------------
            # STEP 2
            # Deliberately stale Page 1 element.
            #
            # This ID existed on Page 1 but must NOT
            # be executable on Page 2.
            # -------------------------------------------------
            {
                "action": "click",
                "element_id": "link_47396bc29f",
            },

            # -------------------------------------------------
            # STEP 3
            # Valid current Page 2 action.
            # -------------------------------------------------
            {
                "action": "click",
                "element_id": "button_f638e4d700",
            },
        ]

        self.index = 0

    def generate(
        self,
        prompt: str,
    ):

        print(
            "\n[FakeLLM] Received planner prompt."
        )

        if self.index >= len(
            self.responses
        ):

            raise RuntimeError(
                "FakeLLM has no more responses."
            )

        response = self.responses[
            self.index
        ]

        self.index += 1

        print(
            "[FakeLLM] Returning:"
        )

        print(
            response
        )

        import json

        return json.dumps(
            response
        )


def main():

    print("⭐ Tara starting...")
    print(
        "🛡️ Milestone 35 stale-reference "
        "safety test...\n"
    )

    browser = Browser(
        headless=False
    )

    try:

        browser.start()

        actions = BrowserActions(
            browser.page
        )

        reader = PageReader(
            browser.page
        )

        planner = AgentPlanner()

        # -----------------------------------------------------
        # Replace Qwen with deterministic test LLM.
        # -----------------------------------------------------

        planner.llm = FakeLLM()

        # -----------------------------------------------------
        # OPEN PAGE ONE
        # -----------------------------------------------------

        test_file = (
            Path(__file__).parent
            / "tests"
            / "state_page1.html"
        )

        test_url = (
            test_file
            .resolve()
            .as_uri()
        )

        print(
            f"[Test] Opening: {test_url}"
        )

        result = actions.navigate(
            test_url
        )

        print(
            f"[Test] Navigation result: {result}"
        )

        # -----------------------------------------------------
        # TASK
        # -----------------------------------------------------

        task = (
            'Click the "Next Page" link, '
            'then click the "Finish" button.'
        )

        print(
            f"\n[Test] Task: {task}"
        )

        # -----------------------------------------------------
        # AGENT
        # -----------------------------------------------------

        agent = AgentLoop(
            reader=reader,
            planner=planner,
            actions=actions,
            max_steps=6,
            max_retries_per_goal=2,
        )

        success = agent.run(
            task
        )

        # -----------------------------------------------------
        # MEMORY
        # -----------------------------------------------------

        memory = agent.last_memory

        failed_actions = []

        if memory is not None:

            failed_actions = (
                memory.failed_actions
            )

        # -----------------------------------------------------
        # CHECK FOR PLANNER ERROR
        # -----------------------------------------------------

        stale_reference_rejected = any(
            action.get("error_type")
            == "PLANNER_ERROR"
            and "invalid action"
            in action.get(
                "error",
                "",
            ).lower()
            for action in failed_actions
        )

        # Milestone 42 validates an invalid historical ID against current
        # candidates before execution and safely falls back when the current
        # candidate is unambiguous.  That is still stale-target rejection,
        # just earlier than the legacy planner-error record.
        stale_reference_rejected = (
            stale_reference_rejected
            or planner.diagnostics.get("invalid_llm_decisions", 0) > 0
        )

        # -----------------------------------------------------
        # CHECK FINAL STATE
        # -----------------------------------------------------

        current_url = (
            browser.page.url
        )

        page_two_url = (
            Path(__file__).parent
            / "tests"
            / "state_page2.html"
        ).resolve().as_uri()

        on_page_two = (
            current_url
            == page_two_url
        )

        # -----------------------------------------------------
        # PRINT RESULTS
        # -----------------------------------------------------

        print(
            "\n" + "=" * 60
        )

        print(
            "[Test] Stale reference rejected: "
            f"{stale_reference_rejected}"
        )

        print(
            "[Test] Final page is Page Two: "
            f"{on_page_two}"
        )

        print(
            "[Test] Failed action records: "
            f"{len(failed_actions)}"
        )

        # -----------------------------------------------------
        # FINAL VALIDATION
        # -----------------------------------------------------

        if (
            success
            and stale_reference_rejected
            and on_page_two
        ):

            print(
                "\n✅ MILESTONE 35 PASSED"
            )

            print(
                "Tara rejected a stale historical "
                "element reference and recovered."
            )

        else:

            print(
                "\n❌ MILESTONE 35 FAILED"
            )

        print(
            "=" * 60
        )

    except Exception as error:

        print(
            "\n❌ TARA ERROR"
        )

        print(
            type(error).__name__
        )

        print(
            error
        )

    finally:

        browser.close()


if __name__ == "__main__":
    main()
