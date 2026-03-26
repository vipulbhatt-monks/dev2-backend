from typing import Any, Dict, List, Optional
from db.crud import (
    get_or_create_chat_session,
    save_message,
    get_messages,
    get_or_create_project_for_session
)
from models.requirement_models import MessagePart


async def initialize_session(
    session_id: str,
    session_type: str = "agent",
    #project_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
# only call project creation if we actually need a new session
    existing = get_or_create_chat_session(
        session_id=session_id,
        session_type=session_type
    )
    if existing.get("project_id"):
        return existing # returning user, project already linked
    # new session, no project yet
    project = get_or_create_project_for_session(session_id)
    # backfill project_id onto the session
    return get_or_create_chat_session(
        session_id=session_id,
        session_type=session_type,
        project_id=project["id"],
        user_id=user_id
    )


async def persist_message(
    session_id: str,
    role: str,
    parts: List[MessagePart]
) -> None:
    try:
        content = [part.dict() for part in parts]
        save_message(session_id=session_id, role=role, content=content)
    except Exception as e:
        print(f"[ChatService] Failed to save message: {e}")


async def load_history(session_id: str) -> List[Dict[str, Any]]:
    try:
        return get_messages(session_id)
    except Exception as e:
        print(f"[ChatService] Failed to load history: {e}")
        return []