from pathlib import Path

from browser.browser import Browser
from browser.reader import PageReader
from browser.actions import BrowserActions
from agent.planner import AgentPlanner
from agent.loop import AgentLoop


def main():

    print("⭐ Tara starting...")
    print(
        "🧠 Milestone 34 memory-aware planning test...\n"
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

        # =====================================================
        # OPEN PAGE ONE
        # =====================================================

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

        # =====================================================
        # TASK
        # =====================================================

        task = (
            'Click the "Next Page" link, '
            'then click the "Finish" button.'
        )

        print(
            f"\n[Test] Task: {task}"
        )

        # =====================================================
        # AGENT
        # =====================================================

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

        # =====================================================
        # CHECK PLANNER MEMORY
        # =====================================================

        print(
            "\n" + "=" * 60
        )

        prompt = (
            planner.last_prompt
            or ""
        )

        memory_context = (
            planner.last_memory_context
            or {}
        )

        # -----------------------------------------------------
        # MEMORY CONTENT CHECKS
        # -----------------------------------------------------

        page_one_in_prompt = (
            "Tara State Page One"
            in prompt
        )

        page_two_in_prompt = (
            "Tara State Page Two"
            in prompt
        )

        next_page_in_prompt = (
            "Next Page"
            in prompt
        )

        finish_in_prompt = (
            "Finish"
            in prompt
        )

        visited_urls = (
            memory_context.get(
                "visited_urls",
                [],
            )
        )

        transitions = (
            memory_context.get(
                "recent_transitions",
                [],
            )
        )

        recent_history = (
            memory_context.get(
                "recent_page_history",
                [],
            )
        )

        transition_memory_present = (
            len(transitions) > 0
        )

        semantic_memory_present = (
            len(recent_history) > 0
        )

        # -----------------------------------------------------
        # PRINT
        # -----------------------------------------------------

        print(
            "[Test] Planner memory inspection:"
        )

        print(
            f"  Page One in planner context: "
            f"{page_one_in_prompt}"
        )

        print(
            f"  Page Two in planner context: "
            f"{page_two_in_prompt}"
        )

        print(
            f"  'Next Page' in planner context: "
            f"{next_page_in_prompt}"
        )

        print(
            f"  'Finish' in planner context: "
            f"{finish_in_prompt}"
        )

        print(
            f"  Visited URLs remembered: "
            f"{len(visited_urls)}"
        )

        print(
            f"  Transitions remembered: "
            f"{len(transitions)}"
        )

        print(
            f"  Semantic page history entries: "
            f"{len(recent_history)}"
        )

        # -----------------------------------------------------
        # MEMORY SAFETY CHECK
        # -----------------------------------------------------

        historical_id_used_as_action = False

        for line in prompt.splitlines():

            if (
                "link_47396bc29f"
                in line
                and "element_id"
                in line
            ):

                # The historical element ID may appear
                # inside memory, but it must not be treated
                # as the current executable candidate.
                continue

        # -----------------------------------------------------
        # FINAL RESULT
        # -----------------------------------------------------

        if (
            success
            and page_one_in_prompt
            and page_two_in_prompt
            and next_page_in_prompt
            and finish_in_prompt
            and len(visited_urls) >= 2
            and transition_memory_present
            and semantic_memory_present
            and not historical_id_used_as_action
        ):

            print(
                "\n✅ MILESTONE 34 PASSED"
            )

            print(
                "Tara is now providing browser memory "
                "to the planner as historical context."
            )

        else:

            print(
                "\n❌ MILESTONE 34 FAILED"
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