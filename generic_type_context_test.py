"""Regression: generic type actions prefer unused form fields over search/reuse."""
from agent.planner import AgentPlanner
from browser.state import InputState, PageState


def field(identifier, name, label, kind="text", role=None):
    return InputState(id=identifier, tag="INPUT", type=kind, name=name, label=label,
                      selector="#" + identifier, visible=True, enabled=True, role=role)


def main():
    page = PageState(url="local://form", title="Form", headings=[], links=[], buttons=[], text="", inputs=[
        field("input_search", "site_query", "Search site", "search", "searchbox"),
        field("input_first", "given_value", "Given value"),
        field("input_technical", "lname", "lname"),
        field("input_second", "family_value", "Family value"),
        field("input_email", "email", "Email"),
    ])
    planner = AgentPlanner()
    candidates = planner.build_candidates(page, 'Type "Lovelace".',
        completed_actions=[{"action": "type", "element_id": "input_first", "text": "Ada"}])
    types = [candidate for candidate in candidates if candidate["action"] == "type"]
    assert types[0]["label"] == "Family value", types
    assert "meaningful_user_facing_label" in types[0]["score_reasons"]
    first = next(item for item in types if item["element_id"] == "input_first")
    search = next(item for item in types if item["element_id"] == "input_search")
    technical = next(item for item in types if item["element_id"] == "input_technical")
    assert "previously_used_field_penalty" in first["score_reasons"]
    assert "search_field_penalty" in search["score_reasons"]
    assert types[0]["score"] > technical["score"]
    print("GENERIC TYPE CONTEXT PASSED")


if __name__ == "__main__": main()
