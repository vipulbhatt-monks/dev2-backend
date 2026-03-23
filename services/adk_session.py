"""
Singleton wrappers around Google ADK's session and runner infrastructure.
Import `get_runner` and `get_session_service` wherever you need them.
"""

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from agents.srs_agent import srs_agent

# ---------------------------------------------------------------------------
# One session service and one runner for the whole app lifetime.
# For multi-process / multi-replica deployments replace InMemorySessionService
# with a persistent backend (e.g. google.adk.sessions.DatabaseSessionService).
# ---------------------------------------------------------------------------

_session_service: InMemorySessionService | None = None
_runner: Runner | None = None

APP_NAME = "beebot-srs"


def get_session_service() -> InMemorySessionService:
    global _session_service
    if _session_service is None:
        _session_service = InMemorySessionService()
    return _session_service


def get_runner() -> Runner:
    global _runner
    if _runner is None:
        _runner = Runner(
            agent=srs_agent,
            app_name=APP_NAME,
            session_service=get_session_service(),
        )
    return _runner


async def ensure_session(session_id: str, user_id: str = "user") -> None:
    """Create the ADK session if it does not already exist."""
    svc = get_session_service()
    existing = await svc.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if existing is None:
        await svc.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )