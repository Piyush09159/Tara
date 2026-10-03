from typing import Literal, Optional

from pydantic import BaseModel


class TaskStatus(BaseModel):
    status: Literal[
        "continue",
        "done",
        "failed",
    ]

    reason: Optional[str] = None