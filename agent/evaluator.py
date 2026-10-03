from agent.task import TaskStatus
from agent.semantic import normalize_semantic_key, semantic_keys_match


class TaskEvaluator:

    def _is_first_name_field(self, field) -> bool:
        semantic = " ".join(
            str(value or "")
            for value in [
                field.name,
                field.label,
                field.aria_label,
                field.placeholder,
            ]
        ).lower()

        if "first name" in semantic:
            return True

        if "firstname" in semantic:
            return True

        if "fname" in semantic:
            return True

        normalized = (
            str(field.name or "")
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

        return "first" in normalized

    def _is_last_name_field(self, field) -> bool:
        semantic = " ".join(
            str(value or "")
            for value in [
                field.name,
                field.label,
                field.aria_label,
                field.placeholder,
            ]
        ).lower()

        if "last name" in semantic:
            return True

        if "lastname" in semantic:
            return True

        if "lname" in semantic:
            return True

        normalized = (
            str(field.name or "")
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

        return "last" in normalized

    def _field_matches_fact_key(
        self,
        field,
        fact_key: str,
    ) -> bool:

        key = normalize_semantic_key(fact_key)

        semantic = " ".join(
            str(value or "")
            for value in [
                field.name,
                field.label,
                field.aria_label,
                field.placeholder,
            ]
        ).lower()

        normalized_semantic = normalize_semantic_key(semantic)

        if key == "verification_code":
            return (
                "verification code" in semantic
                or "verification_code" in normalized_semantic
            )

        if key == "reference_number":
            return (
                "reference number" in semantic
                or "reference_number" in normalized_semantic
                or "reference no" in semantic
                or "reference_no" in normalized_semantic
            )

        return semantic_keys_match(key, normalized_semantic)

    def _evaluate_click_goal(
        self,
        page_state,
        goal,
        last_action=None,
    ) -> TaskStatus:

        if last_action is not None:
            if last_action.get("action") != "click":
                return TaskStatus(
                    status="continue",
                    reason=(
                        f'Waiting to click "{goal.target}".'
                    ),
                )

            target_text = (
                last_action.get("target_text")
                or ""
            ).strip().lower()

            expected = (
                str(goal.target or "")
                .strip()
                .lower()
            )

            if target_text == expected:
                return TaskStatus(
                    status="done",
                    reason=(
                        f'Goal verified: "{goal.target}" '
                        "was clicked."
                    ),
                )

        return TaskStatus(
            status="continue",
            reason=(
                f'Waiting to click "{goal.target}".'
            ),
        )

    def _evaluate_navigate_goal(
        self,
        page_state,
        goal,
    ) -> TaskStatus:

        current = (
            str(page_state.url)
            .rstrip("/")
        )

        target = (
            str(goal.target)
            .rstrip("/")
        )

        if current == target:
            return TaskStatus(
                status="done",
                reason=(
                    f"Navigation goal verified: "
                    f"{goal.target}"
                ),
            )

        return TaskStatus(
            status="continue",
            reason=(
                f"Waiting to navigate to "
                f"{goal.target}."
            ),
        )

    def _evaluate_type_goal(
        self,
        page_state,
        goal,
        last_action=None,
        action_result=None,
    ) -> TaskStatus:

        target_value = (
            str(goal.target or "")
        )

        matching_fields = []

        for field in page_state.inputs:

            if not field.visible:
                continue

            semantic_match = False

            description = (
                str(goal.description or "")
                .lower()
            )

            if "first name" in description:
                semantic_match = (
                    self._is_first_name_field(field)
                )

            elif "last name" in description:
                semantic_match = (
                    self._is_last_name_field(field)
                )

            else:
                semantic_match = True

            if semantic_match:
                matching_fields.append(field)

        # Nothing useful on the current page yet.
        if not matching_fields:
            return TaskStatus(
                status="continue",
                reason=(
                    "No matching input field is currently visible."
                ),
            )

        # After an actual action, require that the exact
        # current field received the requested value.
        if last_action is not None:

            if last_action.get("action") != "type":
                return TaskStatus(
                    status="continue",
                    reason="Waiting for the type action.",
                )

            if action_result is not None:
                if not action_result.get("success", False):
                    return TaskStatus(
                        status="failed",
                        reason=(
                            "The type action did not succeed."
                        ),
                    )

            action_text = (
                str(last_action.get("text") or "")
            )

            if target_value:
                if action_text != target_value:
                    return TaskStatus(
                        status="continue",
                        reason=(
                            "The action typed a different value."
                        ),
                    )

            for field in matching_fields:

                if (
                    field.id
                    == last_action.get("element_id")
                ):

                    if (
                        str(field.value or "")
                        == target_value
                    ):
                        return TaskStatus(
                            status="done",
                            reason=(
                                "Type goal verified."
                            ),
                        )

                    return TaskStatus(
                        status="continue",
                        reason=(
                            "The selected field does not yet "
                            "contain the target value."
                        ),
                    )

        # Initial state: don't consider a prefilled field
        # complete; wait for Tara to perform the action.
        return TaskStatus(
            status="continue",
            reason="Waiting for the type action.",
        )

    def _evaluate_type_from_fact_goal(
        self,
        page_state,
        goal,
        last_action=None,
        action_result=None,
    ) -> TaskStatus:

        fact_key = (
            goal.fact_key
            or goal.target
            or ""
        )

        matching_fields = [
            field
            for field in page_state.inputs
            if field.visible
            and self._field_matches_fact_key(
                field,
                fact_key,
            )
        ]

        if not matching_fields:
            return TaskStatus(
                status="continue",
                reason=(
                    "The field matching the remembered "
                    f"fact '{fact_key}' is not visible."
                ),
            )

        if last_action is None:
            return TaskStatus(
                status="continue",
                reason=(
                    f"Waiting to enter the remembered "
                    f"{fact_key.replace('_', ' ')}."
                ),
            )

        if last_action.get("action") != "type":
            return TaskStatus(
                status="continue",
                reason=(
                    "Waiting for the memory-based type action."
                ),
            )

        if action_result is not None:
            if not action_result.get(
                "success",
                False,
            ):
                return TaskStatus(
                    status="failed",
                    reason=(
                        "The memory-based type action failed."
                    ),
                )

        for field in matching_fields:

            if (
                field.id
                == last_action.get("element_id")
            ):

                typed_value = str(
                    last_action.get("text") or ""
                )

                current_value = str(
                    field.value or ""
                )

                if (
                    typed_value
                    and current_value == typed_value
                ):
                    return TaskStatus(
                        status="done",
                        reason=(
                            "Remembered fact was entered "
                            "into the correct field."
                        ),
                    )

                return TaskStatus(
                    status="continue",
                    reason=(
                        "The remembered value has not yet "
                        "been confirmed in the field."
                    ),
                )

        return TaskStatus(
            status="continue",
            reason=(
                "The action did not target the expected "
                "fact field."
            ),
        )

    def _control_matches_goal(self, field, target):
        semantic = normalize_semantic_key(" ".join(str(value or "") for value in
            [field.label, field.aria_label, field.name, field.placeholder]))
        return semantic_keys_match(normalize_semantic_key(target or ""), semantic)

    def _evaluate_select_goal(self, page_state, goal, last_action=None,
                              action_result=None) -> TaskStatus:
        if not last_action or last_action.get("action") != "select":
            return TaskStatus(status="continue", reason="Waiting for the select action.")
        if action_result is not None and not action_result.get("success", False):
            return TaskStatus(status="failed", reason="The select action did not succeed.")
        for field in page_state.inputs:
            if field.id == last_action.get("element_id") and field.tag.upper() == "SELECT":
                expected = str(goal.target or "")
                if semantic_keys_match(expected, field.selected or "") or semantic_keys_match(expected, last_action.get("option") or ""):
                    return TaskStatus(status="done", reason="Select goal verified.")
        return TaskStatus(status="continue", reason="The requested option is not selected.")

    def _evaluate_check_goal(self, page_state, goal, last_action=None,
                             action_result=None) -> TaskStatus:
        if not last_action or last_action.get("action") != "check":
            return TaskStatus(status="continue", reason="Waiting for the check action.")
        if action_result is not None and not action_result.get("success", False):
            return TaskStatus(status="failed", reason="The check action did not succeed.")
        for field in page_state.inputs:
            if field.id == last_action.get("element_id") and field.checked and self._control_matches_goal(field, goal.target):
                return TaskStatus(status="done", reason="Check/radio goal verified.")
        return TaskStatus(status="continue", reason="The requested control is not checked.")

    def evaluate_goal(
        self,
        page_state,
        goal,
        last_action=None,
        action_result=None,
    ) -> TaskStatus:

        if goal.completed:
            return TaskStatus(
                status="done",
                reason="Goal already completed.",
            )

        if goal.goal_type == "click":
            return self._evaluate_click_goal(
                page_state,
                goal,
                last_action=last_action,
            )

        if goal.goal_type == "navigate":
            return self._evaluate_navigate_goal(
                page_state,
                goal,
            )

        if goal.goal_type == "type_from_fact":
            return self._evaluate_type_from_fact_goal(
                page_state,
                goal,
                last_action=last_action,
                action_result=action_result,
            )

        if goal.goal_type == "type":
            return self._evaluate_type_goal(
                page_state,
                goal,
                last_action=last_action,
                action_result=action_result,
            )

        if goal.goal_type == "select":
            return self._evaluate_select_goal(page_state, goal, last_action, action_result)

        if goal.goal_type == "check":
            return self._evaluate_check_goal(page_state, goal, last_action, action_result)

        return TaskStatus(
            status="continue",
            reason="Unknown goal type.",
        )

    def evaluate(
        self,
        page_state,
        task,
        last_action=None,
    ) -> TaskStatus:

        """
        Backward-compatible helper retained for older tests.

        For direct click tasks it behaves like the legacy evaluator.
        """

        goal_text = str(task)

        if "click" in goal_text.lower():
            return TaskStatus(
                status="done"
                if last_action
                else "continue",
                reason=(
                    "Legacy click evaluation."
                ),
            )

        return TaskStatus(
            status="continue",
            reason=(
                "Use evaluate_goal for goal-driven execution."
            ),
        )
