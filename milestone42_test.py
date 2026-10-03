"""Deterministic candidate-ranking and invalid-LLM fallback test."""
import json
from agent.planner import AgentPlanner
from browser.state import PageState, InputState

class InvalidLLM:
    def generate(self, prompt):
        return json.dumps({"action": "type", "element_id": "invented", "text": "Ada"})

def main():
    fields = [
        InputState(id="input_first", tag="INPUT", type="text", name="first_name", label="First Name", selector="#first", visible=True, enabled=True),
        InputState(id="input_last", tag="INPUT", type="text", name="last_name", label="Last Name", selector="#last", visible=True, enabled=True),
    ]
    state = PageState(url="file:///m42", title="M42", headings=[], links=[], buttons=[], inputs=fields, text="")
    planner = AgentPlanner(); planner.llm = InvalidLLM()
    action = planner.plan(state, 'Enter "Ada" as the first name.')
    assert action.element_id == "input_first"
    assert planner.diagnostics["candidate_count_after_filter"] == 1
    assert planner.diagnostics["invalid_llm_decisions"] == 1
    assert planner.diagnostics["fallback_selections"] == 1
    print("MILESTONE 42 DETERMINISTIC PASSED")

if __name__ == "__main__": main()
