import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BrowserSnapshot(BaseModel):

    step: int

    url: str

    title: str

    fingerprint: str

    headings: List[str] = Field(
        default_factory=list
    )

    links: List[Dict[str, Any]] = Field(
        default_factory=list
    )

    buttons: List[Dict[str, Any]] = Field(
        default_factory=list
    )

    inputs: List[Dict[str, Any]] = Field(
        default_factory=list
    )

    text_excerpt: str = ""


class BrowserTransition(BaseModel):

    step: int

    from_url: str

    to_url: str

    action: str

    success: bool

    navigated: bool = False
    state_changed: bool = False
    page_identity: Optional[str] = None


class BrowserMemory(BaseModel):

    snapshots: List[BrowserSnapshot] = Field(
        default_factory=list
    )

    transitions: List[BrowserTransition] = Field(
        default_factory=list
    )

    visited_urls: List[str] = Field(
        default_factory=list
    )

    # =========================================================
    # BUILD SEMANTIC STATE
    # =========================================================

    def _build_semantic_state(
        self,
        page_state,
    ):

        # -----------------------------------------------------
        # LINKS
        # -----------------------------------------------------

        links = []

        for link in page_state.links[:20]:

            links.append(
                {
                    "id": link.id,
                    "text": link.text,
                    "href": link.href,
                    "visible": link.visible,
                    "enabled": link.enabled,
                }
            )

        # -----------------------------------------------------
        # BUTTONS
        # -----------------------------------------------------

        buttons = []

        for button in page_state.buttons[:20]:

            buttons.append(
                {
                    "id": button.id,
                    "text": button.text,
                    "aria_label": button.aria_label,
                    "visible": button.visible,
                    "enabled": button.enabled,
                }
            )

        # -----------------------------------------------------
        # INPUTS
        # -----------------------------------------------------

        inputs = []

        for field in page_state.inputs[:20]:

            inputs.append(
                {
                    "id": field.id,
                    "tag": field.tag,
                    "type": field.type,
                    "name": field.name,
                    "label": field.label,
                    "aria_label": field.aria_label,
                    "placeholder": field.placeholder,
                    # Browser snapshots are persisted/planner-visible. A
                    # password value belongs only in the live browser field.
                    "value": "<REDACTED>" if str(field.type or "").lower() == "password" else field.value,
                    "visible": field.visible,
                    "enabled": field.enabled,
                }
            )

        # -----------------------------------------------------
        # TEXT
        # -----------------------------------------------------

        text_excerpt = (
            page_state.text or ""
        ).strip()

        if len(text_excerpt) > 1500:

            text_excerpt = (
                text_excerpt[:1500]
                + "..."
            )

        # -----------------------------------------------------
        # COMPLETE SEMANTIC STATE
        # -----------------------------------------------------

        return {
            "url": page_state.url,
            "title": page_state.title,
            "headings": page_state.headings[:10],
            "links": links,
            "buttons": buttons,
            "inputs": inputs,
            "text_excerpt": text_excerpt,
        }

    # =========================================================
    # FINGERPRINT
    # =========================================================

    def _make_fingerprint(
        self,
        semantic_state,
    ):

        serialized = json.dumps(
            semantic_state,
            sort_keys=True,
            ensure_ascii=False,
        )

        return hashlib.sha1(
            serialized.encode("utf-8")
        ).hexdigest()

    # =========================================================
    # SNAPSHOT
    # =========================================================

    def record_snapshot(
        self,
        step: int,
        page_state,
    ):

        semantic_state = (
            self._build_semantic_state(
                page_state
            )
        )

        fingerprint = (
            self._make_fingerprint(
                semantic_state
            )
        )

        # -----------------------------------------------------
        # CHANGE DETECTION
        # -----------------------------------------------------

        if self.snapshots:

            previous_snapshot = (
                self.snapshots[-1]
            )

            if (
                previous_snapshot.fingerprint
                == fingerprint
            ):

                # Same meaningful page state.
                # Do not create a duplicate snapshot.
                return {
                    "changed": False,
                    "snapshot": previous_snapshot,
                    "fingerprint": fingerprint,
                }

        # -----------------------------------------------------
        # CREATE SNAPSHOT
        # -----------------------------------------------------

        snapshot = BrowserSnapshot(
            step=step,
            url=semantic_state["url"],
            title=semantic_state["title"],
            fingerprint=fingerprint,
            headings=semantic_state[
                "headings"
            ],
            links=semantic_state[
                "links"
            ],
            buttons=semantic_state[
                "buttons"
            ],
            inputs=semantic_state[
                "inputs"
            ],
            text_excerpt=semantic_state[
                "text_excerpt"
            ],
        )

        self.snapshots.append(
            snapshot
        )

        # -----------------------------------------------------
        # VISITED URL
        # -----------------------------------------------------

        if (
            page_state.url
            not in self.visited_urls
        ):

            self.visited_urls.append(
                page_state.url
            )

        # -----------------------------------------------------
        # MEMORY LIMITS
        # -----------------------------------------------------

        if len(self.snapshots) > 15:

            self.snapshots = (
                self.snapshots[-15:]
            )

        if len(self.visited_urls) > 30:

            self.visited_urls = (
                self.visited_urls[-30:]
            )

        return {
            "changed": True,
            "snapshot": snapshot,
            "fingerprint": fingerprint,
        }

    # =========================================================
    # TRANSITION
    # =========================================================

    def record_transition(
        self,
        step: int,
        from_url: str,
        to_url: str,
        action: str,
        success: bool,
        navigated: bool = False,
        state_changed: bool = False,
        page_identity: Optional[str] = None,
    ):

        transition = BrowserTransition(
            step=step,
            from_url=from_url,
            to_url=to_url,
            action=action,
            success=success,
            navigated=navigated,
            state_changed=state_changed,
            page_identity=page_identity,
        )

        self.transitions.append(
            transition
        )

        if (
            to_url
            not in self.visited_urls
        ):

            self.visited_urls.append(
                to_url
            )

        if len(self.transitions) > 20:

            self.transitions = (
                self.transitions[-20:]
            )

        return transition

    # =========================================================
    # CURRENT SNAPSHOT
    # =========================================================

    def recent_snapshot(
        self,
    ) -> Optional[BrowserSnapshot]:

        if not self.snapshots:
            return None

        return self.snapshots[-1]

    # =========================================================
    # RECENT TRANSITION
    # =========================================================

    def recent_transition(
        self,
    ) -> Optional[BrowserTransition]:

        if not self.transitions:
            return None

        return self.transitions[-1]

    # =========================================================
    # FIND SNAPSHOTS FOR URL
    # =========================================================

    def snapshots_for_url(
        self,
        url: str,
    ):

        return [
            snapshot
            for snapshot in self.snapshots
            if snapshot.url == url
        ]

    # =========================================================
    # PAGE HISTORY
    # =========================================================

    def semantic_history(
        self,
    ):

        history = []

        for snapshot in self.snapshots[-5:]:

            history.append(
                {
                    "step": snapshot.step,
                    "url": snapshot.url,
                    "title": snapshot.title,
                    "fingerprint": (
                        snapshot.fingerprint
                    ),
                    "headings": (
                        snapshot.headings
                    ),
                    "links": snapshot.links,
                    "buttons": snapshot.buttons,
                    "inputs": snapshot.inputs,
                    "text_excerpt": (
                        snapshot.text_excerpt
                    ),
                }
            )

        return history

    # =========================================================
    # PLANNER CONTEXT
    # =========================================================

    def planner_context(
        self,
    ):

        return {
            "visited_urls": (
                self.visited_urls[-15:]
            ),

            "recent_page_history": (
                self.semantic_history()
            ),

            "recent_transitions": [
                transition.model_dump()
                for transition
                in self.transitions[-10:]
            ],
        }
