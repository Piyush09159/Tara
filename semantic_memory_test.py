from pathlib import Path

from browser.browser import Browser
from browser.reader import PageReader
from browser.actions import BrowserActions
from agent.planner import AgentPlanner
from agent.loop import AgentLoop


def main():

    print("⭐ Tara starting...")
    print(
        "🧠 Milestone 33 "
        "browser-state change detection test...\n"
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
        # MEMORY
        # =====================================================

        print(
            "\n" + "=" * 60
        )

        if agent.last_memory is None:

            print(
                "❌ No working memory was produced."
            )

            print(
                "❌ MILESTONE 33 FAILED"
            )

            return

        browser_memory = (
            agent.last_memory.browser
        )

        snapshots = (
            browser_memory.snapshots
        )

        visited_urls = (
            browser_memory.visited_urls
        )

        transitions = (
            browser_memory.transitions
        )

        # -----------------------------------------------------
        # PAGE SEMANTICS
        # -----------------------------------------------------

        page_one_found = any(
            (
                snapshot.title
                == "Tara State Page One"
            )
            for snapshot in snapshots
        )

        page_two_found = any(
            (
                snapshot.title
                == "Tara State Page Two"
            )
            for snapshot in snapshots
        )

        next_page_found = any(
            any(
                link.get("text")
                == "Next Page"
                for link in snapshot.links
            )
            for snapshot in snapshots
        )

        finish_found = any(
            any(
                button.get("text")
                == "Finish"
                for button
                in snapshot.buttons
            )
            for snapshot in snapshots
        )

        # -----------------------------------------------------
        # FINGERPRINT CHECK
        # -----------------------------------------------------

        fingerprints = [
            snapshot.fingerprint
            for snapshot in snapshots
        ]

        unique_fingerprints = set(
            fingerprints
        )

        no_duplicate_snapshots = (
            len(fingerprints)
            == len(unique_fingerprints)
        )

        # -----------------------------------------------------
        # STATE COUNT
        # -----------------------------------------------------

        # There should be exactly two meaningful page states:
        #
        # 1. State Page One
        # 2. State Page Two
        #
        # Repeated observations of Page Two must
        # not create additional snapshots.

        expected_state_count = 2

        correct_state_count = (
            len(snapshots)
            == expected_state_count
        )

        # -----------------------------------------------------
        # PRINT RESULTS
        # -----------------------------------------------------

        print(
            "[Test] Semantic snapshots:"
        )

        print(
            f"  Count: "
            f"{len(snapshots)}"
        )

        print(
            f"  Expected: "
            f"{expected_state_count}"
        )

        print(
            f"  Page One remembered: "
            f"{page_one_found}"
        )

        print(
            f"  Page Two remembered: "
            f"{page_two_found}"
        )

        print(
            f"  'Next Page' remembered: "
            f"{next_page_found}"
        )

        print(
            f"  'Finish' remembered: "
            f"{finish_found}"
        )

        print(
            f"  Unique fingerprints: "
            f"{len(unique_fingerprints)}"
        )

        print(
            f"  Duplicate snapshots: "
            f"{not no_duplicate_snapshots}"
        )

        print(
            f"  Visited URLs: "
            f"{len(visited_urls)}"
        )

        print(
            f"  Browser transitions: "
            f"{len(transitions)}"
        )

        # -----------------------------------------------------
        # FINGERPRINT DISPLAY
        # -----------------------------------------------------

        print(
            "\n[Test] Stored state fingerprints:"
        )

        for snapshot in snapshots:

            print(
                f"  STEP {snapshot.step}: "
                f"{snapshot.title} "
                f"→ "
                f"{snapshot.fingerprint[:12]}"
            )

        # =====================================================
        # FINAL VALIDATION
        # =====================================================

        if (
            success
            and page_one_found
            and page_two_found
            and next_page_found
            and finish_found
            and len(visited_urls) >= 2
            and len(transitions) == 2
            and correct_state_count
            and no_duplicate_snapshots
        ):

            print(
                "\n✅ MILESTONE 33 PASSED"
            )

            print(
                "Tara detected repeated browser "
                "states and avoided duplicate "
                "semantic snapshots."
            )

        else:

            print(
                "\n❌ MILESTONE 33 FAILED"
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