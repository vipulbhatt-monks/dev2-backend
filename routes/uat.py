import json
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from services.ai_service import generate_text

router = APIRouter(prefix="/api/uat", tags=["uat"])

class UATGenerateRequest(BaseModel):
    requirements: Dict[str, str]
    query: Optional[str] = None

UAT_SYSTEM_PROMPT = """
You are a senior QA engineer with expertise in writing User Acceptance Testing (UAT) test cases for software products.

Your task is to generate comprehensive UAT test cases from the provided software requirements.

GUIDELINES:
- Cover both happy path (expected normal usage) and edge cases (empty inputs, invalid data, boundary conditions).
- Each test case must be specific and independently executable by a non-technical tester.
- Write descriptions in plain English — avoid technical jargon.
- expectedResult must be precise and observable (e.g. "User sees a success toast message and is redirected to the dashboard").
- Group test cases by feature area where possible (use the id prefix, e.g. TC-AUTH-001, TC-DASH-001).
- Aim for full coverage of each requirement — at least one happy path and one edge case per major feature.

Return ONLY a JSON array of objects. Each object MUST match this schema exactly:
[
  {
    "id": "TC-XXX-001",
    "description": "string",
    "expectedResult": "string",
    "actualResult": "",
    "status": "Pending"
  }
]

Rules:
- Return ONLY JSON (no markdown, no explanation).
- "actualResult" must always be an empty string.
- "status" must always be "Pending".
- Generate between 8 and 15 test cases.
"""

from fastapi.responses import StreamingResponse
from services.ai_service import generate_content_stream

@router.post("/generate")
async def generate_uat(request: UATGenerateRequest):
    async def stream_uat():
        try:
            req_text = json.dumps(request.requirements, indent=2)
            prompt = f"Generate UAT test cases for these requirements:\n\n{req_text}"
            if request.query:
                prompt += f"\n\nUSER REQUEST/FOCUS AREA: {request.query}\nPlease generate or update test cases specifically focusing on this request."
            
            async for chunk in generate_content_stream(
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                system_instruction=UAT_SYSTEM_PROMPT,
                temperature=0.3
            ):
                # We yield the text part of the chunk
                if hasattr(chunk, "text") and chunk.text:
                    yield chunk.text
        except Exception as e:
            yield json.dumps({"error": str(e)})

    return StreamingResponse(stream_uat(), media_type="text/event-stream")
