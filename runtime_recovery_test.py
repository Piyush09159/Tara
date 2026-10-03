from pathlib import Path

from browser.browser import Browser
from browser.reader import PageReader
from browser.actions import BrowserActions
from agent.planner import AgentPlanner
from agent.loop import AgentLoop


class FaultInjectingActions(BrowserActions):

    def __init__(self, page):
        super().__init__(page)

        self.failure_injected = False

    def type(
        self,
        element_id: str,
        text: str,
    ):
        # Inject exactly one deterministic failure.
        if not self.failure_injected:

            self.failure_injected = True

            print(
                "[TEST] ⚠️ Injecting artificial "
                "ELEMENT_DISABLED failure."
            )

            return {
                "success": False,
                "action": "type",
                "error_type": (
                    "ELEMENT_DISABLED"
                ),
                "error": (
                    "Injected failure for "
                    "Milestone 28."
                ),
                "element_id": element_id,
                "text": text,
            }

        # All subsequent actions behave normally.
        return super().type(
            element_id,
            text,
        )


def main():

    print("⭐ Tara starting...")
    print("🧪 Milestone 28 runtime recovery test...\n")

    browser = Browser(
        headless=False
    )

    try:

        browser.start()

        actions = FaultInjectingActions(
            browser.page
        )

        reader = PageReader(
            browser.page
        )

        planner = AgentPlanner()

        # -----------------------------------------------------
        # OPEN LOCAL TEST PAGE
        # -----------------------------------------------------

        test_file = (
            Path(__file__).parent
            / "tests"
            / "recovery_runtime_test.html"
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
            'Enter "Piyush" as the first name.'
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
        # RESULT
        # -----------------------------------------------------

        print(
            "\n" + "=" * 60
        )

        if success:

            print(
                "✅ MILESTONE 28 PASSED"
            )

            print(
                "Tara recovered from a runtime "
                "action failure."
            )

        else:

            print(
                "❌ MILESTONE 28 FAILED"
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