from pydantic import BaseModel
from typing import Optional


class CurrentUser(BaseModel):
    user_id: str
    session_id: Optional[str] = None
