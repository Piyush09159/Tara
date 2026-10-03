from pathlib import Path

from browser.browser import Browser
from browser.reader import PageReader
from browser.actions import BrowserActions
from agent.planner import AgentPlanner
from agent.loop import AgentLoop


def main():

    print("⭐ Tara starting...")
    print("🧪 Milestone 27 recovery test...\n")

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
        # OPEN LOCAL TEST PAGE
        # -----------------------------------------------------

        test_file = (
            Path(__file__).parent
            / "tests"
            / "recovery_test.html"
        )

        test_url = test_file.resolve().as_uri()

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
                "✅ MILESTONE 27 PASSED"
            )

            print(
                "Tara successfully completed the "
                "task using recovery."
            )

        else:

            print(
                "❌ MILESTONE 27 FAILED"
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