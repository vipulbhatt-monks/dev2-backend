from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class MessagePart(BaseModel):
    text: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None
    function_response: Optional[Dict[str, Any]] = None


class Message(BaseModel):
    role: str
    parts: List[MessagePart]


class ChatRequest(BaseModel):
    message: Optional[str] = None
    history: List[Message]
    tool_responses: Optional[List[Dict[str, Any]]] = None
    session_id: Optional[str] = "default-agent"       # ← added


class GenerateProjectRequest(BaseModel):
    requirements: Dict[str, str]
    projectName: Optional[str] = "project-specs"
    session_id: Optional[str] = "default-agent"
    wireframe: Optional[Dict[str, Any]] = None


def convert_history_to_contents(history: List[Message]) -> List[dict]:
    contents: List[dict] = []
    for msg in history:
        parts: List[dict] = []
        if msg.parts:
            for p in msg.parts:
                if p.text is not None:
                    parts.append({"text": p.text})
                elif p.function_call is not None:
                    parts.append({"function_call": p.function_call})
                elif p.function_response is not None:
                    parts.append({"function_response": p.function_response})

        if not parts:
            continue

        contents.append({"role": msg.role, "parts": parts})

    return contents
