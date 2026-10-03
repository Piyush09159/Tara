import re
from typing import List, Optional

from pydantic import BaseModel, Field

from agent.semantic import normalize_semantic_key


class Goal(BaseModel):
    id: int
    description: str
    goal_type: str
    target: Optional[str] = None
    fact_key: Optional[str] = None
    completed: bool = False


class GoalPlan(BaseModel):
    goals: List[Goal] = Field(default_factory=list)

    @property
    def completed_count(self) -> int:
        return sum(
            1 for goal in self.goals
            if goal.completed
        )

    @property
    def total_count(self) -> int:
        return len(self.goals)

    @property
    def is_complete(self) -> bool:
        return (
            self.total_count > 0
            and self.completed_count == self.total_count
        )

    def current_goal(self) -> Optional[Goal]:
        for goal in self.goals:
            if not goal.completed:
                return goal
        return None


class GoalDecomposer:
    """
    Convert a natural-language browser task into ordered goals.

    Supported goal families:
      - click
      - navigate
      - type
      - type_from_fact

    type_from_fact is used when the user refers to a semantic
    value that should be obtained from TaskContextMemory.
    """

    def _quoted_values(self, task: str):
        return re.findall(
            r"""["']([^"']+)["']""",
            task,
        )

    def _click_goals(self, task: str):
        return re.findall(
            r"""(?:click|press)\s+(?:the\s+)?["']([^"']+)["']""",
            task,
            flags=re.IGNORECASE,
        )

    def _fact_goal_matches(self, task: str):
        matches = []

        pattern = re.compile(
            r"(?:enter|type|write|fill|use)\s+(?:the\s+)?"
            r"([A-Za-z][A-Za-z _-]{1,60}?)"
            r"(?=\s+(?:in|into|on|to)\b|[.,;]|$)",
            flags=re.IGNORECASE,
        )

        for match in pattern.finditer(task):
            readable = match.group(1).strip()
            fact_key = normalize_semantic_key(readable)

            if not fact_key:
                continue

            matches.append(
                (
                    match.start(),
                    fact_key,
                    f"Enter the {readable.lower()}.",
                )
            )

        matches.sort(key=lambda item: item[0])
        return matches

    def _named_type_goals(self, task: str):
        goals = []

        patterns = [
            (
                "first_name",
                "first name",
            ),
            (
                "last_name",
                "last name",
            ),
            ("email", "email"),
            ("password", "password"),
        ]

        for fact_key, readable in patterns:
            match = re.search(
                rf"""
                (?:
                    enter|
                    type|
                    write|
                    fill
                )
                \s+
                (?:the\s+)?
                {re.escape(readable)}
                \s+
                (?:as\s+)?
                ["']([^"']+)["']
                """,
                task,
                flags=re.IGNORECASE | re.VERBOSE,
            )

            if match:
                goals.append(
                    (
                        match.start(),
                        fact_key,
                        readable,
                        match.group(1),
                    )
                )

            # Also support natural reverse phrasing used by main.py:
            # Enter "Ada" as the first name.
            reverse_match = re.search(
                rf'''(?:enter|type|write|fill)\s+["']([^"']+)["']
                    \s+as\s+(?:the\s+)?{re.escape(readable)}''',
                task,
                flags=re.IGNORECASE | re.VERBOSE,
            )
            if reverse_match:
                goals.append((reverse_match.start(), fact_key, readable,
                              reverse_match.group(1)))

        goals.sort(key=lambda item: item[0])
        return goals

    def _generic_type_goals(self, task: str):
        """
        Preserve the existing generic quoted-value behavior.

        Values already attached to click goals or named fields are
        excluded from the generic type-goal list.
        """

        quoted = self._quoted_values(task)
        click_values = {
            value.strip().lower()
            for value in self._click_goals(task)
        }
        control_values = {
            match.group(1).strip().lower()
            for match in re.finditer(
                r'''(?:select|choose|check|accept)\s+(?:the\s+)?["']([^"']+)["']''',
                task, flags=re.IGNORECASE,
            )
        }

        named_values = set()

        for item in self._named_type_goals(task):
            named_values.add(
                item[3].strip().lower()
            )

        results = []

        for value in quoted:
            normalized = value.strip().lower()

            if not normalized:
                continue

            if normalized in click_values:
                continue

            if normalized in control_values:
                continue

            if normalized in named_values:
                continue

            results.append(value)

        return results

    def decompose(self, task: str) -> GoalPlan:
        goals = []

        # -----------------------------------------------------
        # Collect ordered intent fragments.
        # -----------------------------------------------------

        fragments = []

        for match in re.finditer(
            r"""(?:click|press)\s+(?:the\s+)?["']([^"']+)["']""",
            task,
            flags=re.IGNORECASE,
        ):
            fragments.append(
                (
                    match.start(),
                    "click",
                    match.group(1),
                    None,
                )
            )

        # Explicit form-control intents stay separate from clicks/types so
        # planning and verification can require the correct control state.
        for match in re.finditer(
            r'''select\s+(?:the\s+)?["']([^"']+)["']''',
            task, flags=re.IGNORECASE,
        ):
            fragments.append((match.start(), "select", match.group(1), None))

        # "Choose" is commonly used for radio options.  Model it as a
        # checked control; select menus retain the explicit "select" verb.
        for match in re.finditer(
            r'''choose\s+(?:the\s+)?["']([^"']+)["']''',
            task, flags=re.IGNORECASE,
        ):
            fragments.append((match.start(), "check", match.group(1), None))

        for match in re.finditer(
            r'''(?:check|accept)\s+(?:the\s+)?["']([^"']+)["']''',
            task, flags=re.IGNORECASE,
        ):
            fragments.append((match.start(), "check", match.group(1), None))

        for match in re.finditer(
            r"""(?:https?|file)://[^\s"']+""",
            task,
            flags=re.IGNORECASE,
        ):
            url = match.group(0).rstrip(".,)")
            fragments.append(
                (
                    match.start(),
                    "navigate",
                    url,
                    None,
                )
            )

        for position, fact_key, readable, value in (
            self._named_type_goals(task)
        ):
            fragments.append(
                (
                    position,
                    "type",
                    readable,
                    value,
                )
            )

        for position, fact_key, description in (
            self._fact_goal_matches(task)
        ):
            fragments.append(
                (
                    position,
                    "type_from_fact",
                    description,
                    fact_key,
                )
            )

        # If the task is a simple quoted-value typing task,
        # preserve legacy generic typing.
        for value in self._generic_type_goals(task):
            position = task.lower().find(
                value.lower()
            )

            fragments.append(
                (
                    position if position >= 0 else len(task),
                    "type",
                    f'Type "{value}".',
                    value,
                )
            )

        fragments.sort(
            key=lambda item: item[0]
        )

        next_id = 1

        for _, goal_type, target_or_description, extra in (
            fragments
        ):
            if goal_type == "click":
                goals.append(
                    Goal(
                        id=next_id,
                        description=(
                            f'Click "{target_or_description}"'
                        ),
                        goal_type="click",
                        target=target_or_description,
                    )
                )

            elif goal_type == "navigate":
                goals.append(
                    Goal(
                        id=next_id,
                        description=(
                            f"Navigate to {target_or_description}"
                        ),
                        goal_type="navigate",
                        target=target_or_description,
                    )
                )

            elif goal_type == "type":
                if target_or_description in {
                    "first name",
                    "last name",
                    "email",
                    "password",
                }:
                    readable = target_or_description
                    value = extra

                    goals.append(
                        Goal(
                            id=next_id,
                            description=(
                                f'Enter "{value}" as '
                                f"the {readable}."
                            ),
                            goal_type="type",
                            target=value,
                        )
                    )
                else:
                    goals.append(
                        Goal(
                            id=next_id,
                            description=target_or_description,
                            goal_type="type",
                            target=extra,
                        )
                    )

            elif goal_type == "type_from_fact":
                goals.append(
                    Goal(
                        id=next_id,
                        description=target_or_description,
                        goal_type="type_from_fact",
                        fact_key=extra,
                        target=extra,
                    )
                )

            elif goal_type in {"select", "check"}:
                verb = "Select" if goal_type == "select" else "Check"
                goals.append(Goal(id=next_id,
                                  description=f'{verb} "{target_or_description}"',
                                  goal_type=goal_type,
                                  target=target_or_description))

            next_id += 1

        return GoalPlan(goals=goals)
