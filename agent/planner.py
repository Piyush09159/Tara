import json
import re

from llm.ollama_client import OllamaClient
from agent.action import BrowserAction
from agent.semantic import normalize_semantic_key, semantic_keys_match
from agent.target import SemanticTarget


class AgentPlanner:

    def __init__(self):

        self.llm = OllamaClient()

        # Debug / inspection fields.
        # These let us verify exactly what memory
        # was provided to the planner.
        self.last_prompt = None
        self.last_memory_context = None
        self.last_decision_type = None
        self.diagnostics = {
            "candidate_count_before_filter": 0,
            "candidate_count_after_filter": 0,
            "top_k_count": 0,
            "llm_calls": 0,
            "invalid_llm_decisions": 0,
            "deterministic_selections": 0,
            "fallback_selections": 0,
        }
        self.top_k_candidates = 5

    # =========================================================
    # TEXT EXTRACTION
    # =========================================================

    def extract_quoted_values(
        self,
        task: str,
    ):

        return re.findall(
            r'["\']([^"\']+)["\']',
            task,
        )

    def extract_click_goals(
        self,
        task: str,
    ):

        return re.findall(
            r'(?:click|press)\s+'
            r'(?:the\s+)?["\']([^"\']+)["\']',
            task,
            flags=re.IGNORECASE,
        )

    # =========================================================
    # CANDIDATE GENERATION
    # =========================================================

    # =========================================================
    # TASK MEMORY VALUE EXTRACTION
    # =========================================================

    def extract_task_fact_values(
        self,
        task,
        memory_context=None,
    ):
        """
        Find semantic task-memory facts that are relevant to
        the current task.

        Example:

            task:
                "Enter the verification code."

            memory:
                verification_code = STAR-742

            result:
                ["STAR-742"]
        """

        if not memory_context:
            return []

        normalized_task = normalize_semantic_key(task)

        task_context = memory_context.get(
            "task_context",
            {},
        )

        facts = task_context.get(
            "facts",
            [],
        )

        values = []

        for fact in facts:

            key = str(
                fact.get("key", "")
            ).strip().lower()

            value = str(
                fact.get("value", "")
            ).strip()

            if not key or not value:
                continue

            if key in normalized_task:

                if value not in values:
                    values.append(value)

        return values

    def _fact_keys_for_task(self, task, memory_context=None):
        if not memory_context:
            return []

        normalized_task = normalize_semantic_key(task)
        facts = memory_context.get("task_context", {}).get("facts", [])

        return [
            normalize_semantic_key(fact.get("key", ""))
            for fact in facts
            if normalize_semantic_key(fact.get("key", ""))
            and normalize_semantic_key(fact.get("key", "")) in normalized_task
        ]

    def build_candidates(
        self,
        page_state,
        task,
        completed_actions=None,
        failed_actions=None,
        memory_context=None,
    ):

        if completed_actions is None:
            completed_actions = []

        if failed_actions is None:
            failed_actions = []

        task_lower = task.lower()

        candidates = []

        # =====================================================
        # FAILED ACTION SIGNATURES
        # =====================================================

        failed_signatures = set()

        for action in failed_actions:

            if not action.get(
                "blacklist",
                True,
            ):
                continue

            signature = (
                action.get("action"),
                action.get("element_id"),
                action.get("text"),
                action.get("url"),
                action.get("key"),
                action.get("option"),
            )

            failed_signatures.add(
                signature
            )

        def is_failed(candidate):

            signature = (
                candidate.get("action"),
                candidate.get("element_id"),
                candidate.get("text"),
                candidate.get("url"),
                candidate.get("key"),
                candidate.get("option"),
            )

            return signature in failed_signatures

        # =====================================================
        # DIRECT URL NAVIGATION
        # =====================================================

        url_match = re.search(
            r'(?:https?|file)://[^\s"\']+',
            task,
        )

        if url_match:

            requested_url = (
                url_match.group(0)
                .rstrip(".,)")
            )

            current_url = (
                page_state.url
                .rstrip("/")
            )

            target_url = (
                requested_url
                .rstrip("/")
            )

            candidate = {
                "action": "navigate",
                "url": target_url,
                "score": 100,
            }

            if (
                current_url != target_url
                and not is_failed(candidate)
            ):

                candidates.append(
                    candidate
                )

        # =====================================================
        # CLICK
        # =====================================================

        click_goals = (
            self.extract_click_goals(
                task
            )
        )

        completed_clicks = []

        for action in completed_actions:

            if action.get("action") != "click":
                continue

            target_text = (
                action.get("target_text")
                or ""
            ).strip().lower()

            if target_text:

                completed_clicks.append(
                    target_text
                )

        next_click_goal = None

        for goal in click_goals:

            if (
                goal.strip().lower()
                not in completed_clicks
            ):

                next_click_goal = (
                    goal.strip().lower()
                )

                break

        if any(
            word in task_lower
            for word in [
                "click",
                "open",
                "follow",
                "visit",
            ]
        ):

            # -------------------------------------------------
            # LINKS
            # -------------------------------------------------

            for link in page_state.links:

                if not link.visible:
                    continue

                if not link.enabled:
                    continue

                text = (
                    link.text or ""
                ).strip()

                if not text:
                    continue

                score = 0

                semantic = " ".join(
                    str(value or "")
                    for value in [
                        text,
                        link.href,
                    ]
                ).lower()

                if (
                    next_click_goal
                    and text.lower()
                    == next_click_goal
                ):

                    score += 100

                for word in task_lower.split():

                    if (
                        len(word) >= 3
                        and word in semantic
                    ):

                        score += 2

                candidate = {
                    "action": "click",
                    "element_id": link.id,
                    "text": text,
                    "href": link.href,
                    "visible": link.visible,
                    "enabled": link.enabled,
                    "score": score,
                }

                if not is_failed(candidate):

                    candidates.append(
                        candidate
                    )

            # -------------------------------------------------
            # BUTTONS
            # -------------------------------------------------

            for button in page_state.buttons:

                if not button.visible:
                    continue

                if not button.enabled:
                    continue

                text = (
                    button.text or ""
                ).strip()

                if not text:
                    continue

                score = 0

                semantic = " ".join(
                    str(value or "")
                    for value in [
                        text,
                        button.aria_label,
                    ]
                ).lower()

                if (
                    next_click_goal
                    and text.lower()
                    == next_click_goal
                ):

                    score += 100

                for word in task_lower.split():

                    if (
                        len(word) >= 3
                        and word in semantic
                    ):

                        score += 2

                candidate = {
                    "action": "click",
                    "element_id": button.id,
                    "text": text,
                    "aria_label": button.aria_label,
                    "visible": button.visible,
                    "enabled": button.enabled,
                    "score": score,
                }

                if not is_failed(candidate):

                    candidates.append(
                        candidate
                    )

        # =====================================================
        # TYPE
        # =====================================================

        if any(
            word in task_lower
            for word in [
                "type",
                "enter",
                "write",
                "fill",
            ]
        ):

            values = (
                self.extract_quoted_values(
                    task
                )
            )

            # -------------------------------------------------
            # TASK MEMORY VALUES
            # -------------------------------------------------
            # If the task does not explicitly provide a quoted
            # value, look for a matching semantic fact.

            if not values:

                memory_values = (
                    self.extract_task_fact_values(
                        task,
                        memory_context,
                    )
                )

                values.extend(
                    memory_values
                )

            fact_keys = self._fact_keys_for_task(
                task,
                memory_context,
            )

            for field in page_state.inputs:

                if not field.visible:
                    continue

                if not field.enabled:
                    continue

                if field.tag.upper() not in {"INPUT", "TEXTAREA"}:
                    continue

                field_type = (
                    field.type or ""
                ).lower()

                fillable_types = {
                    "",
                    "text",
                    "email",
                    "search",
                    "tel",
                    "url",
                    "password",
                    "number",
                }

                if (
                    field.tag.upper() == "INPUT"
                    and field_type
                    not in fillable_types
                ):

                    continue

                semantic = " ".join(
                    str(value or "")
                    for value in [
                        field.name,
                        field.label,
                        field.aria_label,
                        field.placeholder,
                    ]
                ).lower()

                normalized_field_semantic = normalize_semantic_key(
                    semantic
                )

                score = 0

                # -------------------------------------------------
                # FIRST NAME
                # -------------------------------------------------

                if "first name" in task_lower:

                    if "first name" in semantic:
                        score += 30

                    if "fname" in semantic:
                        score += 30

                    if "firstname" in semantic:
                        score += 30

                    field_name = (
                        field.name or ""
                    ).lower()

                    normalized_field_name = (
                        field_name
                        .replace("-", "_")
                        .replace(" ", "_")
                    )

                    if (
                        "first"
                        in normalized_field_name
                    ):

                        score += 30

                # -------------------------------------------------
                # LAST NAME
                # -------------------------------------------------

                if "last name" in task_lower:

                    if "last name" in semantic:
                        score += 30

                    if "lname" in semantic:
                        score += 30

                    if "lastname" in semantic:
                        score += 30

                    field_name = (
                        field.name or ""
                    ).lower()

                    normalized_field_name = (
                        field_name
                        .replace("-", "_")
                        .replace(" ", "_")
                    )

                    if (
                        "last"
                        in normalized_field_name
                    ):

                        score += 30

                # -------------------------------------------------
                # EMAIL
                # -------------------------------------------------

                if "email" in task_lower:

                    if "email" in semantic:
                        score += 30

                # -------------------------------------------------
                # PASSWORD
                # -------------------------------------------------

                if "password" in task_lower:

                    if "password" in semantic:
                        score += 30

                # -------------------------------------------------
                # SEARCH
                # -------------------------------------------------

                if "search" in task_lower:

                    if "search" in semantic:
                        score += 30

                # A semantic task fact should prefer the current field whose
                # label/name expresses the same normalized concept.
                matching_fact_key = next(
                    (
                        fact_key
                        for fact_key in fact_keys
                        if semantic_keys_match(
                            fact_key,
                            normalized_field_semantic,
                        )
                    ),
                    None,
                )

                if matching_fact_key:
                    score += 40

                # A remembered fact names a semantic destination.  Do not
                # offer unrelated current fields merely because they are
                # fillable: that would make a fact action ambiguous and can
                # leak a value into the wrong field.
                if fact_keys and not matching_fact_key:
                    continue

                if not field.value:
                    score += 5

                # -------------------------------------------------
                # CREATE CANDIDATE
                # -------------------------------------------------

                for value in values:

                    candidate = {
                        "action": "type",
                        "element_id": field.id,
                        "text": value,
                        "text_options": values,
                        "name": field.name,
                        "label": field.label,
                        "aria_label": field.aria_label,
                        "placeholder": field.placeholder,
                        "current_value": field.value,
                        "visible": field.visible,
                        "enabled": field.enabled,
                        "score": score,
                    }

                    if matching_fact_key:
                        candidate["semantic_target"] = (
                            SemanticTarget(
                                target_type="field",
                                semantic_key=matching_fact_key,
                                display_text=(
                                    field.label
                                    or field.aria_label
                                    or field.name
                                    or field.placeholder
                                    or matching_fact_key
                                ),
                                element_id=field.id,
                            ).model_dump()
                        )

                    if not is_failed(candidate):

                        candidates.append(
                            candidate
                        )

        # =====================================================
        # SELECT / CHECK / RADIO
        # =====================================================

        quoted_controls = self.extract_quoted_values(task)
        control_target = quoted_controls[0] if quoted_controls else ""
        normalized_target = normalize_semantic_key(control_target)

        if any(word in task_lower for word in ["select", "choose"]):
            for field in page_state.inputs:
                if field.tag.upper() != "SELECT" or not field.visible or not field.enabled:
                    continue
                for option in field.options:
                    option_key = normalize_semantic_key(option)
                    if normalized_target and not semantic_keys_match(normalized_target, option_key):
                        continue
                    score = 70 if normalized_target == option_key else 45
                    candidate = {"action": "select", "element_id": field.id,
                                 "option": option, "label": field.label,
                                 "name": field.name, "role": field.role,
                                 "visible": field.visible, "enabled": field.enabled,
                                 "score": score,
                                 "score_reasons": ["select_option_match"]}
                    if not is_failed(candidate):
                        candidates.append(candidate)

        if any(word in task_lower for word in ["check", "accept", "choose"]):
            for field in page_state.inputs:
                kind = (field.type or "").lower()
                if kind not in {"checkbox", "radio"} or not field.visible or not field.enabled:
                    continue
                semantic = normalize_semantic_key(" ".join(str(value or "") for value in
                    [field.label, field.aria_label, field.name, field.placeholder]))
                if normalized_target and not semantic_keys_match(normalized_target, semantic):
                    continue
                score = 70 if normalized_target and semantic_keys_match(normalized_target, semantic) else 30
                candidate = {"action": "check", "element_id": field.id,
                             "label": field.label, "name": field.name,
                             "control_type": kind, "role": field.role,
                             "visible": field.visible, "enabled": field.enabled,
                             "score": score,
                             "score_reasons": ["control_label_match"]}
                if not is_failed(candidate):
                    candidates.append(candidate)

        # =====================================================
        # SORT
        # =====================================================

        self.diagnostics["candidate_count_before_filter"] = len(candidates)

        # For an explicitly named field, exclude fields that are clearly a
        # different semantic concept. Generic quoted-value tasks keep their
        # broader candidate set for backwards compatibility.
        named_field = None
        for name in ("first name", "last name", "email", "password", "search"):
            if name in task_lower:
                named_field = name
                break

        if named_field:
            named_tokens = set(normalize_semantic_key(named_field).split("_"))
            filtered = []
            for candidate in candidates:
                if candidate.get("action") != "type":
                    filtered.append(candidate)
                    continue
                field_text = normalize_semantic_key(" ".join(str(candidate.get(key) or "") for key in ("name", "label", "aria_label", "placeholder")))
                field_tokens = set(field_text.split("_"))
                if named_tokens.issubset(field_tokens):
                    candidate.setdefault("score_reasons", []).append("named_field_match")
                    filtered.append(candidate)
            if filtered:
                candidates = filtered

        self.diagnostics["candidate_count_after_filter"] = len(candidates)

        candidates.sort(
            key=lambda item: item.get(
                "score",
                0,
            ),
            reverse=True,
        )

        return candidates[:8]

    # =========================================================
    # MEMORY SUMMARY
    # =========================================================

    def build_memory_context(self, memory):
        """
        Build a compact, planner-safe representation of working memory.

        Important distinction:

        Browser memory contains historical browser structure.
        Task context contains semantic facts discovered during the task.

        Historical element IDs/selectors are informational only and
        must never become executable actions.
        """

        context = memory.planner_context()

        browser_state = context.get(
            "browser_state",
            {},
        )

        recent_page_history = (
            browser_state.get(
                "recent_page_history",
                [],
            )
        )

        compact_page_history = []

        # Planner context is intentionally smaller than BrowserMemory: retain
        # only the three newest snapshots and compact each structural list.
        for page in recent_page_history[-3:]:

            compact_page_history.append(
                {
                    "step": page.get("step"),
                    "url": page.get("url"),
                    "title": page.get("title"),
                    "headings": page.get("headings", [])[:6],
                    "links": page.get("links", [])[:6],
                    "buttons": page.get("buttons", [])[:6],
                    "inputs": page.get("inputs", [])[:6],
                    "text_excerpt": page.get("text_excerpt", "")[:500],
                }
            )

        recent_transitions = (
            browser_state.get(
                "recent_transitions",
                [],
            )
        )

        # ---------------------------------------------------------
        # TASK CONTEXT
        # ---------------------------------------------------------
        #
        # This is semantic information discovered on previous
        # pages, such as:
        #
        # verification_code = STAR-742
        #
        # It is deliberately kept separate from browser elements.
        # ---------------------------------------------------------

        task_context = context.get(
            "task_context",
            {
                "fact_count": 0,
                "facts": [],
            },
        )

        compact_task_facts = []

        for fact in task_context.get(
            "facts",
            [],
        ):

            compact_task_facts.append(
                {
                    "key": fact.get("key"),
                    "value": fact.get("value"),
                    "source_url": fact.get(
                        "source_url",
                        "",
                    ),
                    "source_step": fact.get(
                        "source_step",
                        0,
                    ),
                    "confidence": fact.get(
                        "confidence",
                        1.0,
                    ),
                    "evidence": fact.get(
                        "evidence",
                        "",
                    ),
                }
            )

        return {
            "task": context.get(
                "task",
                "",
            ),

            "current_step": context.get(
                "current_step",
                0,
            ),

            "current_goal_id": context.get(
                "current_goal_id"
            ),

            "recent_actions": context.get(
                "recent_actions",
                [],
            ),

            "recent_failures": context.get(
                "recent_failures",
                [],
            ),

            "recent_recovery": context.get(
                "recent_recovery",
                [],
            ),

            "goal_history": context.get(
                "goal_history",
                [],
            ),

            # -----------------------------------------------------
            # TASK FACT MEMORY
            # -----------------------------------------------------

            "task_context": {
                "fact_count": len(
                    compact_task_facts
                ),
                "facts": compact_task_facts,
            },

            # -----------------------------------------------------
            # BROWSER MEMORY
            # -----------------------------------------------------

            "browser_state": {
                "visited_urls": browser_state.get("visited_urls", [])[-8:],

                "recent_page_history": (
                    compact_page_history
                ),

                "recent_transitions": (
                    recent_transitions[-5:]
                ),
            },
    }
    # =========================================================
    # PROMPT
    # =========================================================

    def create_prompt(
        self,
        page_state,
        task,
        candidates,
        completed_actions,
        failed_actions,
        memory_context=None,
    ):

        candidate_text = json.dumps(
            candidates,
            indent=2,
        )

        completed_text = json.dumps(
            completed_actions,
            indent=2,
        )

        failed_text = json.dumps(
            failed_actions,
            indent=2,
        )

        memory_text = json.dumps(
            memory_context or {},
            indent=2,
        )

        return f"""
You are Tara, a local browser agent.

USER TASK:
{task}

CURRENT PAGE:
URL: {page_state.url}
TITLE: {page_state.title}

CURRENT PAGE TEXT:
{page_state.text}

VALID CURRENT ACTION CANDIDATES:
{candidate_text}

RECENT COMPLETED ACTIONS:
{completed_text}

RECENT FAILED ACTIONS:
{failed_text}

BROWSER WORKING MEMORY:
{memory_text}

MEMORY RULES:

1. Use browser memory as historical context.
2. Historical page elements explain what Tara has seen before.
3. Historical element IDs are NOT executable.
4. Execute ONLY an element from the CURRENT
   VALID ACTION CANDIDATES list.
5. Use previous page transitions to understand how
   Tara reached the current page.
6. Use previous page semantics when interpreting
   the user's current goal.
7. Never assume that an element remembered from a
   previous page still exists on the current page.
8. Prefer the current page when it provides sufficient
   evidence.
9. Use memory to resolve context, order, and intent.
10. Task-context facts may provide semantic values needed
    for the current action.
11. When a current candidate contains a value derived from
    task memory, treat that value as the intended task value.
12. Never invent a value when a relevant task-memory fact
    is available.

Choose exactly ONE current candidate that advances
the NEXT unfinished part of the user's task.

ACTION RULES:

1. Choose ONLY from the candidate list.
2. Never invent an element ID.
3. Never invent an action.
4. Never invent text.
5. Only use visible and enabled elements.
6. Pay attention to the order of requested actions.
7. Do not repeat a completed action unnecessarily.
8. Do not select a blacklisted failed action.
9. Prefer the highest-confidence candidate.
10. Return ONLY valid JSON.
11. Do not use markdown.
12. Do not explain your answer.

For CLICK:

{{
    "action": "click",
    "element_id": "link_xxxxxxxxxx"
}}

For TYPE:

{{
    "action": "type",
    "element_id": "input_xxxxxxxxxx",
    "text": "Piyush"
}}

For NAVIGATE:

{{
    "action": "navigate",
    "url": "https://example.com"
}}

For SELECT:

{{
    "action": "select",
    "element_id": "input_xxxxxxxxxx",
    "option": "India"
}}

For CHECK (checkbox or radio):

{{
    "action": "check",
    "element_id": "input_xxxxxxxxxx"
}}
"""

    # =========================================================
    # PLAN
    # =========================================================

    def plan(
        self,
        page_state,
        task,
        memory=None,
        completed_actions=None,
        failed_actions=None,
        allow_deterministic=False,
    ):

        # -----------------------------------------------------
        # MEMORY
        # -----------------------------------------------------

        if memory is not None:

            completed_actions = (
                memory.completed_actions
            )

            failed_actions = (
                memory.failed_actions
            )

            memory_context = (
                self.build_memory_context(
                    memory
                )
            )

        else:

            if completed_actions is None:
                completed_actions = []

            if failed_actions is None:
                failed_actions = []

            memory_context = {}

        # Save for debugging / testing.
        self.last_memory_context = (
            memory_context
        )

        # -----------------------------------------------------
        # CANDIDATES
        # -----------------------------------------------------

        candidates = self.build_candidates(
            page_state,
            task,
            completed_actions,
            failed_actions,
            memory_context,
        )

        if not candidates:

            raise RuntimeError(
                "No valid action candidates remain "
                "after applying recovery filters."
            )

        candidates = candidates[:self.top_k_candidates]
        self.diagnostics["top_k_count"] = len(candidates)

        if allow_deterministic and len(candidates) == 1:
            self.last_decision_type = "deterministic"
            self.diagnostics["deterministic_selections"] += 1
            action = BrowserAction.model_validate(candidates[0])
            action.validate_requirements()
            return action

        self.last_decision_type = "llm"
        self.diagnostics["llm_calls"] += 1

        print(
            "\n[Tara] Candidate actions:"
        )

        for candidate in candidates:

            print(
                f"  - {candidate}"
            )

        # -----------------------------------------------------
        # PROMPT
        # -----------------------------------------------------

        prompt = self.create_prompt(
            page_state,
            task,
            candidates,
            completed_actions,
            failed_actions,
            memory_context,
        )

        # Save exact prompt for inspection.
        self.last_prompt = prompt

        # -----------------------------------------------------
        # LLM
        # -----------------------------------------------------

        response = self.llm.generate(
            prompt
        ).strip()

        # -----------------------------------------------------
        # REMOVE MARKDOWN FENCES
        # -----------------------------------------------------

        if response.startswith("```"):

            response = response.replace(
                "```json",
                "",
            )

            response = response.replace(
                "```",
                "",
            )

            response = response.strip()

        # -----------------------------------------------------
        # JSON
        # -----------------------------------------------------

        try:

            raw_action = json.loads(
                response
            )

        except json.JSONDecodeError as error:

            raise ValueError(
                "Qwen returned invalid JSON:\n"
                f"{response}"
            ) from error

        if not isinstance(
            raw_action,
            dict,
        ):

            raise ValueError(
                "Qwen did not return a JSON object."
            )

        # =====================================================
        # VALIDATE AGAINST CANDIDATES
        # =====================================================

        selected = None

        for candidate in candidates:

            if (
                candidate.get("action")
                != raw_action.get("action")
            ):
                continue

            if candidate["action"] == "navigate":

                if (
                    candidate.get("url")
                    == raw_action.get("url")
                ):

                    selected = candidate
                    break

            else:

                if (
                    candidate.get("element_id")
                    == raw_action.get(
                        "element_id"
                    )
                ):

                    if (
                        candidate["action"]
                        == "type"
                        and candidate.get("text")
                        != raw_action.get(
                            "text"
                        )
                    ):

                        continue

                    if (
                        candidate["action"] == "select"
                        and candidate.get("option") != raw_action.get("option")
                    ):
                        continue

                    selected = candidate
                    break

        if selected is None:
            self.diagnostics["invalid_llm_decisions"] += 1
            # A generic, transparent fallback: only select the highest ranked
            # current candidate when it clearly separates from alternatives.
            top = candidates[0]
            next_score = candidates[1].get("score", 0) if len(candidates) > 1 else -1
            if top.get("score", 0) >= 30 and (len(candidates) == 1 or top.get("score", 0) - next_score >= 15):
                selected = top
                raw_action = {"action": top["action"]}
                if top["action"] == "navigate": raw_action["url"] = top["url"]
                else:
                    raw_action["element_id"] = top["element_id"]
                    if top["action"] == "type": raw_action["text"] = top["text"]
                    if top["action"] == "select": raw_action["option"] = top["option"]
                self.last_decision_type = "fallback"
                self.diagnostics["fallback_selections"] += 1
            else:
                raise ValueError("Qwen selected an invalid action.")

        self.diagnostics["selected_candidate_score"] = selected.get("score", 0)
        self.diagnostics["selected_candidate_reason"] = selected.get("score_reasons", [])

        # =====================================================
        # ELEMENT SAFETY
        # =====================================================

        if selected["action"] != "navigate":

            if not selected.get(
                "visible",
                False,
            ):

                raise ValueError(
                    "Selected element is not visible."
                )

            if not selected.get(
                "enabled",
                False,
            ):

                raise ValueError(
                    "Selected element is disabled."
                )

        # =====================================================
        # STRONGLY TYPED ACTION
        # =====================================================

        action = BrowserAction.model_validate(
            raw_action
        )

        action.validate_requirements()

        return action
