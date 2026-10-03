from browser.browser import Browser
from browser.reader import PageReader
from browser.actions import BrowserActions
from agent.planner import AgentPlanner
from agent.loop import AgentLoop


def main():
    print("⭐ Tara starting...")
    print("🎯 Goal-driven agent test...\n")

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

        actions.navigate(
            "https://www.w3schools.com/html/html_forms.asp"
        )

        task = (
            'Enter "Piyush" as the first name '
            'and "Garg" as the last name.'
        )

        agent = AgentLoop(
            reader=reader,
            planner=planner,
            actions=actions,
            max_steps=8,
        )

        success = agent.run(
            task
        )

        print(
            "\n" + "=" * 60
        )

        if success:
            print(
                "✅ MILESTONE 26 PASSED"
            )
        else:
            print(
                "❌ MILESTONE 26 FAILED"
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