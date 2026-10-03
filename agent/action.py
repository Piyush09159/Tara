from typing import Literal, Optional

from pydantic import BaseModel, Field


class BrowserAction(BaseModel):
    action: Literal[
        "click",
        "type",
        "press",
        "navigate",
        "back",
        "forward",
        "wait",
        "select",
        "check",
        "uncheck",
    ]

    element_id: Optional[str] = None
    text: Optional[str] = None
    key: Optional[str] = None
    url: Optional[str] = None
    option: Optional[str] = None

    seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=30.0,
    )

    def validate_requirements(self):
        if self.action == "click":
            if not self.element_id:
                raise ValueError(
                    "CLICK requires element_id."
                )

        elif self.action == "type":
            if not self.element_id:
                raise ValueError(
                    "TYPE requires element_id."
                )

            if self.text is None:
                raise ValueError(
                    "TYPE requires text."
                )

        elif self.action == "select":
            if not self.element_id:
                raise ValueError("SELECT requires element_id.")
            if self.option is None:
                raise ValueError("SELECT requires option.")

        elif self.action in {"check", "uncheck"}:
            if not self.element_id:
                raise ValueError(
                    f"{self.action.upper()} requires element_id."
                )

        elif self.action == "press":
            if not self.key:
                raise ValueError(
                    "PRESS requires key."
                )

        elif self.action == "navigate":
            if not self.url:
                raise ValueError(
                    "NAVIGATE requires url."
                )

        elif self.action == "wait":
            if self.seconds <= 0:
                raise ValueError(
                    "WAIT requires positive seconds."
                )
