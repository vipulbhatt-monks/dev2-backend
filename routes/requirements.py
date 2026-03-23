import io
import json
import os
import platform
import re
import subprocess
import zipfile
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Standardize keys for SDKs
api_key = os.getenv("API_KEY")
if api_key:
    os.environ["GOOGLE_API_KEY"] = api_key
    os.environ["GEMINI_API_KEY"] = api_key

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from google.adk.events import Event, EventActions
from google.genai import types as genai_types

from agents.srs_agent import _get_store
from models.requirement_models import GenerateProjectRequest, ChatRequest
from services.adk_session import APP_NAME, ensure_session, get_runner
from services.ai_service import generate_text
from services.chat_service import initialize_session, persist_message, load_history
from models.requirement_models import GenerateProjectRequest, ChatRequest, MessagePart

router = APIRouter()
from google.genai._api_client import BaseApiClient

_original_aclose = BaseApiClient.aclose

async def _safe_aclose(self):
    if hasattr(self, "_async_httpx_client"):
        await _original_aclose(self)

BaseApiClient.aclose = _safe_aclose

# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helper: convert ADK Events → NDJSON chunks the front-end already understands
# ---------------------------------------------------------------------------

def _event_to_payload(event: Event) -> dict | None:
    """
    Map an ADK Event to the same NDJSON schema the original server produced:
      { "text": "..." }          – streamed text delta
      { "function_calls": [...]} – tool invocation
      { "error": "..." }         – error
    Returns None if nothing should be forwarded to the client.
    """
    payload: dict = {}

    # --- text delta ---
    if event.content and event.content.parts:
        text_parts = [p.text for p in event.content.parts if getattr(p, "text", None)]
        if text_parts:
            payload["text"] = "".join(text_parts)

    # --- tool / function calls ---
    if event.content and event.content.parts:
        fn_calls = [
            {
                "name": p.function_call.name,
                "args": dict(p.function_call.args) if p.function_call.args else {},
                "id": getattr(p.function_call, "id", None),
            }
            for p in event.content.parts
            if getattr(p, "function_call", None)
        ]
        if fn_calls:
            payload["function_calls"] = fn_calls

    return payload if payload else None


# ---------------------------------------------------------------------------
# Simple chat (unchanged semantics, now backed by a minimal ADK agent)
# ---------------------------------------------------------------------------

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

_chat_session_svc = InMemorySessionService()
_chat_agent = LlmAgent(
    name="BeeBotChat",
    model="gemini-3-flash-preview",
    instruction="You are BeeBot. Give concise Markdown responses.",
)
_chat_runner = Runner(
    agent=_chat_agent,
    app_name="beebot-chat",
    session_service=_chat_session_svc,
)


@router.post("/chat")
async def chat_stream(request: ChatRequest):
    session_id = request.session_id or "default-chat"
    user_id = "user"

    # Ensure session exists
    existing = await _chat_session_svc.get_session(
        app_name="beebot-chat", user_id=user_id, session_id=session_id
    )
    if not existing:
        await _chat_session_svc.create_session(
            app_name="beebot-chat", user_id=user_id, session_id=session_id
        )

    message_text = request.message or ""

    async def generate():
        try:
            async for event in _chat_runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=message_text)],
                ),
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if getattr(part, "text", None):
                            yield part.text
        except AttributeError as exc:
            if "_async_httpx_client" not in str(exc):
                yield f"\n\n**Error**: {exc}"                    
        except Exception as exc:
            yield f"\n\n**Error**: {exc}"

    return StreamingResponse(generate(), media_type="text/plain")


# ---------------------------------------------------------------------------
# Agent chat  (SRS architect)
# ---------------------------------------------------------------------------

@router.post("/agent/chat")
async def agent_chat(request: ChatRequest):
    session_id = request.session_id or "default-agent"
    user_id = "user"

    # Initialize DB session
    try:
        await initialize_session(session_id, "agent")
    except Exception as e:
        print(f"[ChatService] Could not initialize session: {e}")

    message_text = request.message or ""

    # No message = history restore request
    if not message_text and not request.tool_responses:
        try:
            messages = await load_history(session_id)
            async def stream_history():
                for msg in messages:
                    text_content = ""
                    for part in msg["content"]:
                        if part.get("text"):
                            text_content += part["text"]
                    if text_content:
                        payload = {
                            "text": text_content,
                            "role": msg["role"]
                        }
                        yield json.dumps(payload) + "\n"
            return StreamingResponse(stream_history(), media_type="application/x-ndjson")
        except Exception as e:
            print(f"[ChatService] Could not load history: {e}")
            return StreamingResponse(iter([]), media_type="application/x-ndjson")

    await ensure_session(session_id, user_id)
    runner = get_runner()

    # Save user message
    if message_text:
        try:
            await persist_message(session_id, "user", [MessagePart(text=message_text)])
        except Exception as e:
            print(f"[ChatService] Could not save user message: {e}")

    # Build the user Content object
    if request.message:
        user_content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=request.message)],
        )
    elif request.tool_responses:
        # ADK handles tool results internally; if the client echoes them back,
        # wrap as function_response parts so the model sees them.
        parts = [
            genai_types.Part(
                function_response=genai_types.FunctionResponse(
                    name=tr["function_response"]["name"],
                    id=tr["function_response"].get("id"),
                    response=tr["function_response"].get("response", {}),
                )
            )
            for tr in request.tool_responses
        ]
        user_content = genai_types.Content(role="user", parts=parts)
    else:
        user_content = genai_types.Content(
            role="user", parts=[genai_types.Part(text="")]
        )

    async def generate_agent():
        full_response = ""
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=user_content,
            ):
                payload = _event_to_payload(event)
                if payload:
                    print(f"[ADK] event → {list(payload.keys())}")
                    yield json.dumps(payload) + "\n"

                    if "text" in payload:
                        full_response += payload["text"]

                    if "function_calls" in payload:
                        for fc in payload["function_calls"]:
                            if fc["name"] in ["request_form", "ask_choice_question", "save_section", "finalize_requirements"]:
                                print(f"[ADK] Interrupting chain after {fc['name']} tool.")
                                # Save partial response before stopping
                                if full_response:
                                    await persist_message(session_id, "assistant", [MessagePart(text=full_response)])
                                return

        except Exception as exc:
            print(f"[ADK] Server Error: {exc}")
            yield json.dumps({"error": str(exc)}) + "\n"

    return StreamingResponse(generate_agent(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Project generation  (unchanged logic, reads from in-memory store)
# ---------------------------------------------------------------------------

ORDERED_SECTIONS = [
    "1. Introduction",
    "2. Overall Description",
    "3. System Features",
    "4. External Interface Requirements",
    "5. Other Nonfunctional Requirements",
    "Appendix B: Analysis Models",
]


def _build_full_doc(project_name: str, requirements: dict) -> str:
    full_doc = f"# {project_name} - Software Requirements Specification\n\n"
    for title in ORDERED_SECTIONS:
        if title in requirements:
            full_doc += f"## {title}\n\n{requirements[title]}\n\n---\n\n"
    for title, content in requirements.items():
        if title not in ORDERED_SECTIONS:
            full_doc += f"## {title}\n\n{content}\n\n---\n\n"
    return full_doc


@router.post("/agent/generate-project")
async def generate_project(request: GenerateProjectRequest):
    folder_name = request.projectName or "project-specs"

    # Prefer requirements from the request body; fall back to session store.
    requirements = request.requirements
    if not requirements:
        store = _get_store(request.session_id or "default-agent")
        requirements = store.get("requirements", {})

    full_doc = _build_full_doc(folder_name, requirements)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{folder_name}/requirements.md", full_doc)
        zf.writestr(
            f"{folder_name}/README.md",
            f"# {folder_name}\n\n1. Unzip this folder.\n2. Open it in Windsurf (or VS Code).",
        )
    zip_buffer.seek(0)

    headers = {"Content-Disposition": f"attachment; filename={folder_name}.zip"}
    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers=headers,
    )


@router.post("/agent/save-local")
async def save_local(request: GenerateProjectRequest):
    folder_name = request.projectName or "project-specs"

    requirements = request.requirements
    if not requirements:
        store = _get_store(request.session_id or "default-agent")
        requirements = store.get("requirements", {})

    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    target_dir = os.path.join(downloads_dir, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    file_path = os.path.join(target_dir, "requirements.md")
    instruction_path = os.path.join(target_dir, "START_HERE.md")
    rules_path = os.path.join(target_dir, ".windsurfrules")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(_build_full_doc(folder_name, requirements))

    with open(rules_path, "w", encoding="utf-8") as f:
        f.writelines([
            "You are an expert Senior Software Engineer.\n",
            f"Current Project: {folder_name}\n",
            "Primary Source of Truth: ./requirements.md\n",
            "Secondary Source of Truth (UI Blueprints): ./blueprints/\n",
            "Goal: Fully implement the requirements and UI designs defined in requirements.md and the blueprints folder.\n",
            "Behavior: Be autonomous. Analyze the requirements/UI, set up the stack, and begin coding.\n",
            "Trigger: If the user says 'Go' or provides an empty prompt, start implementation immediately.\n",
        ])

    # Save Blueprints if available
    if request.wireframe and "screens" in request.wireframe:
        blueprint_dir = os.path.join(target_dir, "blueprints")
        os.makedirs(blueprint_dir, exist_ok=True)
        for i, screen in enumerate(request.wireframe["screens"]):
            screen_id = screen.get("id", f"screen_{i}")
            screen_html = screen.get("html", "")
            if screen_html:
                screen_path = os.path.join(blueprint_dir, f"{screen_id}.html")
                with open(screen_path, "w", encoding="utf-8") as bf:
                    bf.write(screen_html)

    with open(instruction_path, "w", encoding="utf-8") as f:
        f.write(f"# 🚀 Auto-Start Instructions for {folder_name}\n\n")
        f.write("Welcome, Agent. Your task is defined in **requirements.md** and visual blueprints in **/blueprints**.\n\n")
        f.write("## ⚡️ IMMEDIATE ACTION REQUIRED:\n")
        f.write("1. **Read** `requirements.md` and scan the `.html` files in `/blueprints`.\n")
        f.write("2. **Initialize** the project structure.\n")
        f.write("3. **Implement** the core Database Schema based on requirements.\n")
        f.write("4. **Create** the UI components matching the blueprints exactly.\n\n")
        f.write("> **USER INSTRUCTION:** Type 'Go' or 'Start' in Chat to begin.\n")

    abs_path = os.path.abspath(instruction_path)
    opened_locally = False

    # try:
    #     sys_name = platform.system()
    #     if sys_name == "Darwin":
    #         subprocess.Popen(["open", "-a", "Windsurf", target_dir])
    #     elif sys_name == "Windows":
    #         subprocess.Popen(["windsurf", target_dir], shell=True)
    #     else:
    #         subprocess.Popen(["windsurf", target_dir])
    #     opened_locally = True
    # except Exception as exc:
    #     print(f"Failed to open Windsurf: {exc}")
    #     try:
    #         if platform.system() == "Darwin":
    #             subprocess.Popen(["open", target_dir])
    #         elif platform.system() == "Windows":
    #             subprocess.Popen(["explorer", target_dir])
    #         except Exception:
    #             pass
    #         pass
    #     except Exception:
    #         pass

    return {
        "success": True,
        "path": abs_path,
        "folder": target_dir,
        "windsurf_url": f"windsurf://file/{abs_path}",
        "opened_locally": opened_locally,
    }


# ---------------------------------------------------------------------------
# Convenience: read the current session's saved sections (useful for the UI)
# ---------------------------------------------------------------------------

@router.get("/agent/state")
async def get_agent_state(session_id: str = "default-agent"):
    store = _get_store(session_id)
    return {
        "requirements": store.get("requirements", {}),
        "finalized": store.get("finalized", False),
        "project_name": store.get("project_name"),
    }
