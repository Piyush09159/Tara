from typing import Literal, Optional

from pydantic import BaseModel


class SemanticTarget(BaseModel):
    """A current-page browser target paired with its semantic meaning.

    ``element_id`` is deliberately transient: it identifies only the element
    observed on the current PageState and is never stored in TaskContextMemory.
    """

    target_type: Literal["field", "button", "link"]
    semantic_key: str
    display_text: str
    element_id: Optional[str] = None
