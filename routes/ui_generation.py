import json
import re
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from models.ui_models import (
    UIBlueprintError,
    UIBlueprintResponse,
    UIGenerateRequest,
    ScreenProposalRequest,
    ScreenGenerateRequest
)
from services.ui_service import UIServiceError, generate_ui_blueprint
from services.ai_service import generate_text

router = APIRouter(prefix="/ui", tags=["ui"])

@router.post(
    "/generate",
    response_model=UIBlueprintResponse,
    responses={502: {"model": UIBlueprintError}},
)
async def generate_ui(request: UIGenerateRequest):
    try:
        blueprint = await generate_ui_blueprint(request.model_dump())
        return blueprint
    except UIServiceError as e:
        return JSONResponse(
            status_code=502,
            content=UIBlueprintError(error="UI blueprint generation failed", details=str(e)).model_dump(),
        )
    except RuntimeError as e:
        return JSONResponse(
            status_code=502,
            content=UIBlueprintError(error="AI service error", details=str(e)).model_dump(),
        )
    except Exception:
        # Avoid exposing stack traces
        return JSONResponse(
            status_code=500,
            content=UIBlueprintError(error="Internal Server Error").model_dump(),
        )

# ---------------------------------------------------------------------------
# UI / Wireframe: Two-Step Generation
# ---------------------------------------------------------------------------

SCREEN_PROPOSAL_SYSTEM = """
You are a senior UI/UX designer with expertise in product design and information architecture.

Your task is to analyze a product description and identify all the logical screens required to deliver the complete user experience.

GUIDELINES:
- Think in terms of user journeys — what screens does a user move through from entry to goal completion?
- Always include foundational screens (e.g. Landing, Login, Register, Dashboard) plus feature-specific screens.
- Each screen should have a single, clear purpose. Do not combine unrelated functionality into one screen.
- Screen descriptions should mention the key UI elements and actions available on that screen.
- Screen IDs should reflect their role in the app (e.g. "user_dashboard", "product_detail", "checkout_confirm").
- Consider both authenticated and unauthenticated states where relevant.

Return ONLY a JSON object (no commentary, no markdown code fences) matching this exact schema:
{
  "appName": "string",
  "screens": [
    {
      "id": "screen_id",
      "title": "Human Readable Title",
      "description": "Short description of what this screen contains and does"
    }
  ]
}

Rules:
- Generate at least 4 and at most 8 screens.
- screen IDs must be lowercase snake_case, unique.
- Return ONLY the JSON. Nothing else.
"""

@router.post("/screens/propose")
async def propose_screens(request: ScreenProposalRequest):
    user_prompt = request.prompt
    if request.file_content:
        user_prompt += f"\n\nAttached context ({request.file_type}):\n{request.file_content[:4000]}"

    try:
        raw = await generate_text(
            contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
            system_instruction=SCREEN_PROPOSAL_SYSTEM,
            temperature=0.4,
        )
        # Strip markdown code fences if present
        cleaned = re.sub(r"^```[\w]*\n?", "", raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\n?```$", "", cleaned.strip(), flags=re.MULTILINE)
        data = json.loads(cleaned)
        return JSONResponse(content=data)
        
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(exc)})


SCREEN_GENERATE_SYSTEM = """
You are Flash UI. Create a stunning, high-fidelity UI component 


**VISUAL EXECUTION RULES:**
1. **Materiality**: Use the specified metaphor to drive every CSS choice. (e.g. if Risograph, use \`feTurbulence\` for grain and \`mix-blend-mode: multiply\` for ink layering).
2. **Typography**: Use high-quality web fonts. Pair a bold sans-serif with a refined monospace for data.
3. **Motion**: Include subtle, high-performance CSS/JS animations (hover transitions, entry reveals).
4. **IP SAFEGUARD**: No artist names or trademarks. 
5. **Layout**: Be bold with negative space and hierarchy. Avoid generic cards.

Return ONLY a JSON object (no commentary, no markdown code fences) matching this exact schema:
{
  "appName": "string",
  "screens": [
    {
      "id": "screen_id",
      "title": "Human Readable Title",
      "html": "<!DOCTYPE html><html>...</html>",
      "connections": [
        { "to": "other_screen_id", "label": "CTA label" }
      ]
    }
  ]
}

Rules:
- You MUST generate exactly the screens provided in the user's list. Do not add or remove screens.
- Each `html` must be a COMPLETE self-contained HTML document with internal <style> tags
- Connections: Only define the 1-2 most important logical transitions for each screen (the "Happy Path"). Avoid connecting every screen to every other screen.

- Return ONLY the JSON. Nothing else.
"""

@router.post("/screens/generate")
async def generate_screens(request: ScreenGenerateRequest):
    # Construct a strong prompt that forces the exact screens.
    screens_list_str = "\n".join([f"- {s.id} ({s.title}): {s.description}" for s in request.screens])
    
    user_prompt = (
        f"Product description / Prompt: {request.prompt}\n\n"
        f"APPROVED SCREENS TO GENERATE (ONLY GENERATE THESE):\n{screens_list_str}\n\n"
        f"App Name: {request.appName}"
    )

    if request.file_content:
        user_prompt += f"\n\nAttached Context ({request.file_type}):\n{request.file_content[:4000]}"

    try:
        raw = await generate_text(
            contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
            system_instruction=SCREEN_GENERATE_SYSTEM,
            temperature=0.4,
        )
        cleaned = re.sub(r"^```[\w]*\n?", "", raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\n?```$", "", cleaned.strip(), flags=re.MULTILINE)

        # Extract just the JSON object in case AI adds extra text after it
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if not match:
            return JSONResponse(status_code=500, content={"error": "No valid JSON found in AI response"})
        data = json.loads(match.group())
        return JSONResponse(content=data)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(exc)})
