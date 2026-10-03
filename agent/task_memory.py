import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agent.semantic import normalize_semantic_key


class TaskFact(BaseModel):
    """
    A piece of information discovered during the current task.

    Only semantic information is stored here. Browser selectors,
    element IDs, XPath expressions, and DOM paths are deliberately
    excluded so task facts cannot become stale browser actions.
    """

    key: str
    value: str
    source_url: str = ""
    source_step: int = 0
    confidence: float = 1.0
    evidence: str = ""


class TaskContextMemory(BaseModel):
    """Semantic information discovered during the current task."""

    facts: List[TaskFact] = Field(default_factory=list)
    max_facts: int = 50

    def add_fact(
        self,
        key: str,
        value: str,
        source_url: str = "",
        source_step: int = 0,
        confidence: float = 1.0,
        evidence: str = "",
    ) -> TaskFact:

        key = normalize_semantic_key(key)
        value = str(value).strip()

        if not key:
            raise ValueError("Fact key cannot be empty.")

        if not value:
            raise ValueError("Fact value cannot be empty.")

        fact = TaskFact(
            key=key,
            value=value,
            source_url=source_url,
            source_step=source_step,
            confidence=max(0.0, min(1.0, confidence)),
            evidence=evidence[:500],
        )

        for index, existing in enumerate(self.facts):
            if existing.key == key:
                self.facts[index] = fact
                return fact

        self.facts.append(fact)
        if len(self.facts) > self.max_facts:
            self.facts = self.facts[-self.max_facts:]

        return fact

    def get_fact(self, key: str) -> Optional[TaskFact]:
        key = normalize_semantic_key(key)
        for fact in reversed(self.facts):
            if fact.key == key:
                return fact
        return None

    def find_facts(self, query: str) -> List[TaskFact]:
        query = str(query).strip().lower()
        if not query:
            return []

        results = []
        for fact in reversed(self.facts):
            haystack = f"{fact.key} {fact.value} {fact.evidence}".lower()
            if query in haystack:
                results.append(fact)
        return results

    def extract_from_observation(
        self,
        observation: Any,
        step: int = 0,
    ) -> List[TaskFact]:
        """Extract deterministic semantic facts from a page observation."""

        if hasattr(observation, "model_dump"):
            observation = observation.model_dump()

        if not isinstance(observation, dict):
            return []

        text = str(observation.get("text", "")).strip()
        if not text:
            return []

        source_url = str(observation.get("url", ""))
        extracted: List[TaskFact] = []

        verification_patterns = [
            r"\bverification\s+code\b\s*[:#\-]\s*([A-Za-z0-9][A-Za-z0-9_-]{2,})",
            r"\bverification\s+code\b\s+is\s+([A-Za-z0-9][A-Za-z0-9_-]{2,})",
        ]

        for pattern in verification_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                evidence = text[max(0, match.start() - 20):min(len(text), match.end() + 20)].replace("\n", " ").strip()
                extracted.append(
                    self.add_fact(
                        key="verification_code",
                        value=value,
                        source_url=source_url,
                        source_step=step,
                        confidence=0.99,
                        evidence=evidence,
                    )
                )
                break

        reference_pattern = (
            r"\breference\s+(?:number|no\.?)\b\s*[:#\-]\s*"
            r"([A-Za-z0-9][A-Za-z0-9_-]{2,})"
        )
        match = re.search(reference_pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            evidence = text[max(0, match.start() - 20):min(len(text), match.end() + 20)].replace("\n", " ").strip()
            extracted.append(
                self.add_fact(
                    key="reference_number",
                    value=value,
                    source_url=source_url,
                    source_step=step,
                    confidence=0.99,
                    evidence=evidence,
                )
            )

        # A task fact must be an explicitly labelled, compact value.
        # This intentionally accepts identifiers such as "REF-9281", not
        # arbitrary colon-separated prose or full sentences.
        labeled_value_pattern = re.compile(
            r"^\s*([A-Za-z][A-Za-z _-]{1,60}?)\s*:\s*"
            r"([A-Za-z0-9][A-Za-z0-9_-]{2,})\s*$",
            flags=re.MULTILINE,
        )

        for match in labeled_value_pattern.finditer(text):
            label = match.group(1).strip()
            key = normalize_semantic_key(label)
            value = match.group(2).strip()

            # Multi-word labels are a useful conservative boundary: they
            # represent named task concepts while excluding broad labels such
            # as "Note: ..." or "Status: ...".
            if not key or "_" not in key:
                continue

            if any(fact.key == key for fact in extracted):
                continue

            evidence = text[
                max(0, match.start() - 20):min(len(text), match.end() + 20)
            ].replace("\n", " ").strip()

            extracted.append(
                self.add_fact(
                    key=key,
                    value=value,
                    source_url=source_url,
                    source_step=step,
                    confidence=0.95,
                    evidence=evidence,
                )
            )

        return extracted

    def planner_context(self) -> Dict[str, Any]:
        return {
            "fact_count": len(self.facts),
            "facts": [fact.model_dump() for fact in self.facts],
        }

    def summary(self) -> str:
        if not self.facts:
            return "No task facts discovered."
        return "; ".join(f"{fact.key}={fact.value}" for fact in self.facts)
