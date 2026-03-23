import json
from typing import Any, Dict, List, Optional, Tuple

from models.ui_models import UIGenerateCodeResponse
from services.ai_service import generate_text
from services.ui_service import UIServiceError


SYSTEM_PROMPT = (
    "You are a UI code generator. Given a UI blueprint JSON containing screens and their components, "
    "generate HTML and CSS for each screen.\n\n"
    "CRITICAL REQUIREMENTS:\n"
    "- Return ONLY valid JSON. No markdown, no explanation.\n"
    "- Output JSON schema must be exactly:\n"
    "  {\"screens\": [{\"name\": string, \"html\": string, \"css\": string}], \"globalCss\": string|null }\n"
    "- HTML must not contain <script> tags.\n"
    "- Use simple semantic HTML and basic CSS (flex, spacing).\n"
    "- Use class names that are stable and scoped per screen.\n"
)


def _extract_json_candidate(text: str) -> str:
    s = text.strip()

    # If model accidentally wraps JSON in a fenced block, strip it.
    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            s = "\n".join(lines[1:-1]).strip()

    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return s
    return s[start : end + 1]


def _validate_structure(obj: Any) -> Tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "Response is not a JSON object"

    if "screens" not in obj:
        return False, "Missing required key: screens"

    screens = obj.get("screens")
    global_css = obj.get("globalCss", None)

    if not isinstance(screens, list):
        return False, "screens must be an array"

    if global_css is not None and not isinstance(global_css, str):
        return False, "globalCss must be a string or null"

    for i, screen in enumerate(screens):
        if not isinstance(screen, dict):
            return False, f"screens[{i}] must be an object"

        for k in ("name", "html", "css"):
            if k not in screen:
                return False, f"screens[{i}] missing required key: {k}"
            if not isinstance(screen[k], str):
                return False, f"screens[{i}].{k} must be a string"
            if not screen[k].strip():
                return False, f"screens[{i}].{k} must be non-empty"

        html = screen.get("html", "")
        if "<script" in html.lower():
            return False, f"screens[{i}].html must not contain script tags"

    return True, ""


async def generate_ui_code_from_blueprint(
    *,
    blueprint: Dict[str, Any],
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    blueprint_text = json.dumps(blueprint, ensure_ascii=False)
    project_line = f"Project Name: {project_name}\n\n" if project_name else ""

    contents: List[dict] = [
        {
            "role": "user",
            "parts": [
                {
                    "text": (
                        "Generate HTML and CSS for each screen in this UI blueprint.\n\n"
                        + project_line
                        + blueprint_text
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
        UIGenerateCodeResponse.model_validate(obj)
        return obj

    # Retry once with a repair prompt.
    repair_contents: List[dict] = [
        {
            "role": "user",
            "parts": [
                {
                    "text": (
                        "Fix the following so it is ONLY valid JSON matching exactly this schema:\n"
                        "{\"screens\": [{\"name\": string, \"html\": string, \"css\": string}], "
                        "\"globalCss\": string|null}\n\n"
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

    UIGenerateCodeResponse.model_validate(repaired_obj)
    return repaired_obj
