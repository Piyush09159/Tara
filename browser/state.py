from pydantic import BaseModel
from typing import List, Optional


class LinkState(BaseModel):
    id: str
    text: str
    href: Optional[str] = None
    selector: str
    visible: bool = False
    enabled: bool = False
    role: Optional[str] = None
    form_id: Optional[str] = None


class ButtonState(BaseModel):
    id: str
    text: str
    aria_label: Optional[str] = None
    selector: str
    visible: bool = False
    enabled: bool = False
    role: Optional[str] = None
    form_id: Optional[str] = None


class InputState(BaseModel):
    id: str
    tag: str
    type: Optional[str] = None
    name: Optional[str] = None
    placeholder: Optional[str] = None
    aria_label: Optional[str] = None
    label: Optional[str] = None
    value: Optional[str] = None
    selector: str
    visible: bool = False
    enabled: bool = False
    # Compact semantic metadata used for form planning.  These are current
    # page observations, never task-memory facts or durable DOM references.
    role: Optional[str] = None
    aria_labelledby: Optional[str] = None
    checked: Optional[bool] = None
    selected: Optional[str] = None
    options: List[str] = []
    form_id: Optional[str] = None


class PageState(BaseModel):
    url: str
    title: str
    headings: List[str]
    links: List[LinkState]
    buttons: List[ButtonState]
    inputs: List[InputState]
    text: str
    # Compact landmark summary, not a DOM tree.  It helps consumers keep
    # navigation and form controls distinct without increasing prompt size.
    regions: List[str] = []
