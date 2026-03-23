"""
SRS Agent built with Google ADK.
Handles the full IEEE 830 Software Requirements Specification interview flow.
"""
import os
from typing import Any
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Standardize keys for SDKs
api_key = os.getenv("API_KEY")
if api_key:
    os.environ["GOOGLE_API_KEY"] = api_key
    os.environ["GEMINI_API_KEY"] = api_key

# ---------------------------------------------------------------------------
# In-memory store shared across a session (keyed by session_id)
# ---------------------------------------------------------------------------
_session_store: dict[str, dict[str, Any]] = {}
SESSION_LIMIT = 10  # Prevent RAM bloat


def _get_store(session_id: str) -> dict[str, Any]:
    global _session_store

    # Simple cleanup: if we're starting a new session and we're over the limit,
    # pop the first (oldest) key.
    if session_id not in _session_store:
        if len(_session_store) >= SESSION_LIMIT:
            oldest_key = next(iter(_session_store))
            _session_store.pop(oldest_key)

        _session_store[session_id] = {
            "requirements": {},
            "finalized": False,
            "project_name": None
        }

    return _session_store[session_id]


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def save_section(title: str, content: str, session_id: str = "default") -> dict:
    """
    Save the FINALIZED content for a section of the SRS document.

    Args:
        title:      The exact Section title (e.g. '1. Introduction').
        content:    The COMPLETE, DETAILED Markdown content for this section.
        session_id: Injected by the runner – do not send from the UI.
    """
    store = _get_store(session_id)
    store["requirements"][title] = content
    return {"status": "saved", "title": title}


def ask_choice_question(question: str, options: list[str]) -> dict:
    """
    Signal the front-end that the agent wants to present a multiple-choice
    question to the user.  The front-end renders the choices; the user's
    selection is sent back as a normal text message.

    Args:
        question: The clarification question text.
        options:  List of choice strings.
    """
    # This is a 'signal' tool – the actual UI rendering happens on the client.
    return {"question": question, "options": options}


def request_form(title: str, fields: list[dict], description: str = "") -> dict:
    """
    Request structured input from the user via a multi-field form.
    Use this when gathering multiple related parameters at once (e.g. settings,
    feature details, non-functional requirements).

    Args:
        title: Title of the form.
        fields: List of field definitions. Each field must have:
                'name' (ID), 'label', 'type' (text, textarea, radio, select, checkbox).
                'options' (list of strings for radio/select), 'placeholder' (optional).
                'required' (boolean, optional).
        description: Brief instructions for the user.
    """
    return {"title": title, "fields": fields, "description": description, "type": "form"}


def finalize_requirements(projectName: str, session_id: str = "default") -> dict:
    """
    Signal that requirements gathering is complete and the SRS is ready.

    Args:
        projectName: Human-readable name of the project.
        session_id:  Injected by the runner.
    """
    store = _get_store(session_id)
    store["finalized"] = True
    store["project_name"] = projectName
    return {"status": "finalized", "projectName": projectName}


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

AGENT_INSTRUCTION = """
You are a Lead Solutions Architect called BeeBot.

**GOAL**: Conduct a structured interview to build a complete, formal Software
Requirements Specification (SRS) following the IEEE 830 standard.

---

## ⚠️ CRITICAL PROTOCOL

1. **NO CHAT DUMPING** — You are STRICTLY FORBIDDEN from writing the SRS
   content inside the chat bubble.
2. **USE `save_section`** — Whenever you have gathered enough information for
   a section, you MUST call `save_section(title=..., content=...)`.
3. **SECTION BY SECTION** — Gather information for one major section at a time,
   then save it before moving on.
4. **START IMMEDIATELY** — Begin the interview right away by asking about
   **1. Introduction**.

---

## SRS DOCUMENT STRUCTURE  (fill every section)

### 1. Introduction
- 1.1 Purpose
- 1.2 Document Conventions
- 1.3 Intended Audience
- 1.4 Project Scope
- 1.5 References

### 2. Overall Description
- 2.1 Product Perspective
- 2.2 Product Features (Summary)
- 2.3 User Classes and Characteristics
- 2.4 Operating Environment
- 2.5 Design and Implementation Constraints
- 2.6 Assumptions and Dependencies

### 3. System Features  (Detailed Functional Requirements)
- 3.1 Feature 1 — Description, Priority, Stimulus/Response, Functional Reqs
- 3.2 Feature 2 …  (add as many features as the project requires)

### 4. External Interface Requirements
- 4.1 User Interfaces
- 4.2 Hardware Interfaces
- 4.3 Software Interfaces
- 4.4 Communications Interfaces

### 5. Other Nonfunctional Requirements
- 5.1 Performance
- 5.2 Safety
- 5.3 Security
- 5.4 Software Quality Attributes

### Appendix B: Analysis Models
- **MANDATORY**: Include a `mermaid` ```graph TD``` diagram representing
  the System Architecture / Analysis Model.

---

## CONVERSATION LOOP

1. **Introduce** yourself briefly, then start interviewing for *1. Introduction*.
2. **Gather** — ask focused questions to flesh out the current section.
   - Use `ask_choice_question` for simple single-choice prompts.
   - Use `request_form` for complex sections with multiple parameters (e.g. Functional Requirements details, Security settings).
3. **Save** — call `save_section` with the complete Markdown content.
4. **Repeat** — move to the next section until *Appendix B* is saved.
5. **Finish** — call `finalize_requirements(projectName=...)`.

---

## CONTENT GUIDELINES

- Use professional, precise technical language.
- Format the `content` argument with Markdown: `## Subheaders`, bullet points,
  tables where useful.
- Appendix B **must** contain a fenced Mermaid code block.
- Make reasonable inferences rather than asking endless questions — confirm
  with the user before saving.
"""

# Wrap plain functions as ADK FunctionTools
srs_tools = [
    FunctionTool(save_section),
    FunctionTool(ask_choice_question),
    FunctionTool(request_form),
    FunctionTool(finalize_requirements),
]

srs_agent = LlmAgent(
    name="SRSArchitectAgent",
    model="gemini-3-flash-preview",          # stable model
    instruction=AGENT_INSTRUCTION,
    tools=srs_tools,
    # Let the model decide when to call tools
)