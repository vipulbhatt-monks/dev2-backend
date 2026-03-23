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
You are an expert QA Engineer. Given the software requirements, generate a list of UAT (User Acceptance Testing) test cases.
Each test case should have:
1. id: unique string (e.g., TC-001)
2. description: what is being tested
3. expectedResult: what should happen
4. actualResult: empty string
5. status: "Pending"

Return ONLY a JSON array of objects. No markdown, no explanation.
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
