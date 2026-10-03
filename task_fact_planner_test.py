import json

from agent.action import BrowserAction
from agent.memory import WorkingMemory
from agent.planner import AgentPlanner
from browser.state import (
    PageState,
    InputState,
)


class FakeLLM:

    def __init__(self):
        self.last_prompt = ""

    def generate(self, prompt: str) -> str:

        self.last_prompt = prompt

        print(
            "\n[FakeLLM] Planner received task memory:"
        )

        print(
            "  STAR-742 present:",
            "STAR-742" in prompt,
        )

        return json.dumps(
            {
                "action": "type",
                "element_id": (
                    "input_verification_code"
                ),
                "text": "STAR-742",
            }
        )


def main():

    print("\n" + "=" * 60)
    print("MILESTONE 37 - MEMORY-AWARE ACTION PLANNING")
    print("=" * 60)

    # =========================================================
    # TASK
    # =========================================================

    task = (
        "Enter the verification code "
        "in the Verification Code field."
    )

    # =========================================================
    # WORKING MEMORY
    # =========================================================

    memory = WorkingMemory(
        task=task,
    )

    memory.current_step = 3

    memory.add_task_fact(
        key="verification_code",
        value="STAR-742",
        source_url=(
            "file:///tests/"
            "task_context_page_b.html"
        ),
        source_step=2,
        confidence=0.99,
        evidence=(
            "Verification code: STAR-742"
        ),
    )

    print(
        "\n[Memory] Stored fact:"
        " verification_code=STAR-742"
    )

    # =========================================================
    # CURRENT PAGE
    # =========================================================

    verification_input = InputState(
        id="input_verification_code",
        tag="input",
        type="text",
        name="verification_code",
        placeholder="Enter verification code",
        aria_label=None,
        label="Verification Code",
        value="",
        selector="#verification_code",
        visible=True,
        enabled=True,
    )

    page_state = PageState(
        url="file:///tests/task_context_page_c.html",
        title="Tara Task Context - Page C",
        headings=[
            "Page C"
        ],
        links=[],
        buttons=[],
        inputs=[
            verification_input
        ],
        text=(
            "Page C\n"
            "Verification Code"
        ),
    )

    # =========================================================
    # PLANNER
    # =========================================================

    planner = AgentPlanner()

    fake_llm = FakeLLM()

    planner.llm = fake_llm

    # =========================================================
    # PLAN
    # =========================================================

    action = planner.plan(
        page_state=page_state,
        task=task,
        memory=memory,
    )

    # =========================================================
    # VERIFY ACTION
    # =========================================================

    print(
        "\n[Planner] Selected action:"
    )

    print(
        action.model_dump()
    )

    assert isinstance(
        action,
        BrowserAction,
    )

    assert action.action == "type"

    assert (
        action.element_id
        == "input_verification_code"
    )

    assert (
        action.text
        == "STAR-742"
    )

    # =========================================================
    # VERIFY CANDIDATE GENERATION
    # =========================================================

    memory_context = (
        planner.last_memory_context
    )

    assert (
        "STAR-742"
        in json.dumps(
            memory_context
        )
    )

    assert (
        "STAR-742"
        in fake_llm.last_prompt
    )

    print(
        "\n[Test] Task fact reached planner: True"
    )

    print(
        "[Test] Planner generated memory-based "
        "TYPE value: STAR-742"
    )

    print(
        "[Test] Correct input selected: True"
    )

    # =========================================================
    # FINAL
    # =========================================================

    print("\n" + "=" * 60)
    print("✅ MILESTONE 37 PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()