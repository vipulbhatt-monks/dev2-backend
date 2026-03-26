from typing import Any, Dict, List, Optional
from db.session import supabase

#---users---------------------------------------------------------

def ensure_user(
    *,
    clerk_user_id: str,
    email: Optional[str] = None,
) -> Dict[str, Any]:
    if not clerk_user_id:
        raise RuntimeError("Missing clerk_user_id")

    try:
        existing = (
            supabase.table("users")
            .select("*")
            .eq("id", clerk_user_id)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        raise RuntimeError("Failed querying users table") from exc

    existing_error = getattr(existing, "error", None)
    if existing_error:
        raise RuntimeError(f"Failed querying users table: {existing_error}")

    if existing and getattr(existing, "data", None):
        row = existing.data
        if email is not None and row.get("email") != email:
            updated = (
                supabase.table("users")
                .update({"email": email})
                .eq("id", clerk_user_id)
                .execute()
            )
            updated_error = getattr(updated, "error", None)
            if updated_error:
                raise RuntimeError(f"Failed updating users table: {updated_error}")
            if updated.data:
                return updated.data[0]
        return row

    payload: Dict[str, Any] = {"id": clerk_user_id}
    if email is not None:
        payload["email"] = email

    inserted = supabase.table("users").insert(payload).execute()
    inserted_error = getattr(inserted, "error", None)
    if inserted_error:
        raise RuntimeError(f"Failed creating user row: {inserted_error}")
    if not inserted.data:
        raise RuntimeError("Failed to create user")
    return inserted.data[0]


# ── chat_sessions ──────────────────────────────────────────────────────────────

def get_or_create_chat_session(
    session_id: str,
    session_type: str = "agent",
    project_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    response = supabase.table("chat_sessions") \
        .select("*") \
        .eq("session_id", session_id) \
        .eq("session_type", session_type) \
        .maybe_single() \
        .execute()
    # print(f"[DEBUG] response type: {type(response)}")
    # print(f"[DEBUG] response: {response}")

    if response is not None:
        return response

    new_session = {
        "session_id": session_id,
        "session_type": session_type,
        "project_id": project_id,
        "user_id": user_id       # null for now, filled when OAuth lands
    }
    result = supabase.table("chat_sessions").insert(new_session).execute()
    return result.data[0]


# ── messages ───────────────────────────────────────────────────────────────────

def save_message(
    session_id: str,
    role: str,
    content: List[Dict[str, Any]]
) -> Dict[str, Any]:
    session = supabase.table("chat_sessions") \
        .select("id") \
        .eq("session_id", session_id) \
        .maybe_single() \
        .execute()

    if session is None:
        raise RuntimeError(f"Chat session not found for session_id: {session_id}")

    message = {
        "session_id": session.data["id"],
        "role": role,
        "content": content
    }
    response = supabase.table("messages").insert(message).execute()
    return response.data[0]


def get_messages(
    session_id: str,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    session = supabase.table("chat_sessions") \
        .select("id") \
        .eq("session_id", session_id) \
        .maybe_single() \
        .execute()

    if session is None:
        return []

    query = supabase.table("messages") \
        .select("*") \
        .eq("session_id", session.data["id"]) \
        .order("timestamp")

    if limit:
        query = query.limit(limit)

    response = query.execute()
    return response.data or []


# ── requirements ───────────────────────────────────────────────────────────────

def save_requirements(
    project_id: str,
    requirements: Dict[str, str]
) -> bool:
    supabase.table("requirements").delete().eq("project_id", project_id).execute()

    ordered_sections = [
        "1. Introduction",
        "2. Overall Description",
        "3. System Features",
        "4. External Interface Requirements",
        "5. Other Nonfunctional Requirements",
        "Appendix B: Analysis Models"
    ]

    rows = []
    for i, section in enumerate(ordered_sections):
        if section in requirements:
            rows.append({
                "project_id": project_id,
                "section_name": section,
                "content": requirements[section],
                "order_index": i
            })

    for section, content in requirements.items():
        if section not in ordered_sections:
            rows.append({
                "project_id": project_id,
                "section_name": section,
                "content": content,
                "order_index": len(ordered_sections) + len(rows)
            })

    if rows:
        supabase.table("requirements").insert(rows).execute()

    return True


def get_requirements(project_id: str) -> Dict[str, str]:
    response = supabase.table("requirements") \
        .select("*") \
        .eq("project_id", project_id) \
        .order("order_index") \
        .execute()

    return {
        row["section_name"]: row["content"]
        for row in (response.data or [])
    }


# ── ui_blueprints ──────────────────────────────────────────────────────────────

def save_blueprint(
    project_id: str,
    blueprint_data: Dict[str, Any]
) -> Dict[str, Any]:
    response = supabase.table("ui_blueprints").insert({
        "project_id": project_id,
        "blueprint_data": blueprint_data
    }).execute()
    return response.data[0]


def get_blueprint(project_id: str) -> Optional[Dict[str, Any]]:
    response = supabase.table("ui_blueprints") \
        .select("*") \
        .eq("project_id", project_id) \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    if response.data:
        return response.data[0]["blueprint_data"]
    return None


# ── projects ───────────────────────────────────────────────────────────────────

def create_project(
    name: str,
    user_id: Optional[str] = None,
    description: Optional[str] = None
) -> Dict[str, Any]:
    response = supabase.table("projects").insert({
        "name": name,
        "user_id": user_id,
        "description": description
    }).execute()
    return response.data[0]


def get_projects(user_id: str) -> List[Dict[str, Any]]:
    response = supabase.table("projects") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()
    return response.data or []