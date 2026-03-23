import json
from typing import Any, Dict, List, Tuple

from models.ui_models import UIBlueprintResponse
from services.ai_service import generate_text

class UIServiceError(Exception):
    pass


SYSTEM_PROMPT = (
    "Based on structured software requirements, generate:\n\n"
    "1. A list of UI screens\n"
    "2. Components for each screen\n"
    "3. High-level user flows\n\n"
    "Return ONLY valid JSON in this format:\n"
    "{\n\"screens\": [],\n\"userFlows\": []\n}\n\n"
    "Do not include explanations or markdown."
)


def _extract_json_candidate(text: str) -> str:
    s = text.strip()

    # If model accidentally wraps JSON in a fenced block, strip it.
    if s.startswith("```"):
        lines = s.splitlines()
        # Drop first and last fence if present
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            s = "\n".join(lines[1:-1]).strip()

    # Take substring between first '{' and last '}'
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return s
    return s[start : end + 1]


def _validate_structure(obj: Any) -> Tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "Response is not a JSON object"

    if "screens" not in obj or "userFlows" not in obj:
        return False, "Missing required keys: screens, userFlows"

    screens = obj.get("screens")
    flows = obj.get("userFlows")

    if not isinstance(screens, list):
        return False, "screens must be an array"
    if not isinstance(flows, list):
        return False, "userFlows must be an array"

    for i, screen in enumerate(screens):
        if not isinstance(screen, dict):
            return False, f"screens[{i}] must be an object"
        if "name" not in screen or "components" not in screen:
            return False, f"screens[{i}] must contain name and components"
        if not isinstance(screen["name"], str):
            return False, f"screens[{i}].name must be a string"
        if not isinstance(screen["components"], list) or not all(
            isinstance(c, str) for c in screen["components"]
        ):
            return False, f"screens[{i}].components must be an array of strings"

    if not all(isinstance(f, str) for f in flows):
        return False, "userFlows must be an array of strings"

    return True, ""


async def generate_ui_blueprint(requirements: Dict[str, Any]) -> Dict[str, Any]:
    contents: List[dict] = [
        {
            "role": "user",
            "parts": [
                {
                    "text": (
                        "Generate the UI blueprint JSON for the following requirements:\n\n"
                        f"{json.dumps(requirements, ensure_ascii=False)}"
                    )
                }
            ],
        }
    ]

    raw = await generate_text(contents=contents, system_instruction=SYSTEM_PROMPT)

    candidate = _extract_json_candidate(raw)
    try:
        obj = json.loads(candidate)
    except Exception:
        obj = None

    ok, reason = _validate_structure(obj)
    if ok:
        # Extra validation through Pydantic (ensures types)
        UIBlueprintResponse.model_validate(obj)
        return obj

    # Retry once with a repair prompt.
    repair_contents: List[dict] = [
        {
            "role": "user",
            "parts": [
                {
                    "text": (
                        "Fix the following so it is ONLY valid JSON matching exactly this schema:\n"
                        "{\"screens\": [{\"name\": string, \"components\": [string]}], "
                        "\"userFlows\": [string]}\n\n"
                        "Return ONLY the corrected JSON.\n\n"
                        f"BROKEN_OUTPUT:\n{raw}"
                    )
                }
            ],
        }
    ]

    repaired = await generate_text(contents=repair_contents, system_instruction=SYSTEM_PROMPT)
    repaired_candidate = _extract_json_candidate(repaired)

    try:
        repaired_obj = json.loads(repaired_candidate)
    except Exception as e:
        raise UIServiceError("Model did not return valid JSON") from e

    ok2, reason2 = _validate_structure(repaired_obj)
    if not ok2:
        raise UIServiceError(f"Model returned invalid JSON structure: {reason2}")

    UIBlueprintResponse.model_validate(repaired_obj)
    return repaired_obj
