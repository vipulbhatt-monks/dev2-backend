
import logging
import json
import re
import uuid
from typing import List

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from models.jira_models import (
    JiraCreateIssuesResponse,
    JiraDraftStoriesResponse,
    JiraDraftStory,
    JiraIssueCreateError,
    JiraPublishErrorsResponse,
    JiraPublishOkResponse,
    JiraPublishStoriesRequest,
    JiraStory,
)
from services.ai_service import generate_text
from services.jira_service import JiraServiceError, create_story_issue


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jira", tags=["jira"])


async def _create_issues_from_stories(stories: List[JiraStory]) -> JiraCreateIssuesResponse:
    created: List[str] = []
    errors: List[JiraIssueCreateError] = []

    for idx, story in enumerate(stories):
        try:
            key = await create_story_issue(
                summary=story.summary,
                description=story.description,
                issue_type=story.issue_type,
                labels=story.labels,
            )
            created.append(key)
        except JiraServiceError as exc:
            logger.exception("Jira issue creation failed")
            errors.append(
                JiraIssueCreateError(
                    index=idx,
                    summary=getattr(story, "summary", None),
                    error=str(exc),
                    status_code=exc.status_code,
                    jira_response=exc.jira_response,
                )
            )
            continue
        except RuntimeError as exc:
            logger.exception("Jira configuration error")
            return JSONResponse(status_code=500, content={"error": str(exc)})
        except Exception as exc:
            logger.exception("Unexpected error while creating Jira issues")
            errors.append(
                JiraIssueCreateError(
                    index=idx,
                    summary=getattr(story, "summary", None),
                    error=str(exc),
                )
            )
            continue

    return JiraCreateIssuesResponse(created_issues=created, errors=errors)


JIRA_STORIES_FROM_SRS_SYSTEM_PROMPT = """
You are an expert product manager and agile coach. Convert the provided SRS text into Jira stories.

Return ONLY a JSON array of objects. Each object MUST match this schema exactly:
{
  "summary": "string",
  "description": "string",
  "issue_type": "string | null",
  "labels": ["string"]
}

Rules:
- Return ONLY JSON (no markdown, no commentary).
- Generate between 1 and 10 stories.
 - "issue_type" and "labels" are optional; use null or [] if unknown.
"""


@router.post(
    "/issues/draft-from-srs",
    response_model=JiraDraftStoriesResponse,
)
async def draft_issues_from_srs(srs: str = Body(..., media_type="text/plain")):
    try:
        if not (srs or "").strip():
            return JSONResponse(status_code=422, content={"error": "Missing required body"})

        raw = await generate_text(
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Generate Jira story JSON from this SRS. "
                                "Keep it concise but actionable.\n\nSRS:\n"
                                f"{srs}"
                            )
                        }
                    ],
                }
            ],
            system_instruction=JIRA_STORIES_FROM_SRS_SYSTEM_PROMPT,
            temperature=0.3,
        )
        cleaned = re.sub(r"^```[\w]*\n?", "", raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\n?```$", "", cleaned.strip(), flags=re.MULTILINE)

        stories_obj = json.loads(cleaned)
        if not isinstance(stories_obj, list):
            return JSONResponse(
                status_code=502,
                content={"error": "Gemini did not return a JSON array"},
            )

        stories: List[JiraStory] = [JiraStory.model_validate(item) for item in stories_obj]
        stories = stories[:10]

        draft_stories: List[JiraDraftStory] = [
            JiraDraftStory(
                id=str(uuid.uuid4()),
                summary=s.summary,
                description=s.description,
                issue_type=s.issue_type,
                labels=s.labels,
            )
            for s in stories
        ]
        return JiraDraftStoriesResponse(stories=draft_stories)
    except RuntimeError as exc:
        logger.exception("AI service error")
        return JSONResponse(status_code=502, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Failed to generate draft stories from SRS")
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post(
    "/issues/publish",
    response_model=JiraPublishOkResponse,
)
async def publish_issues(request: JiraPublishStoriesRequest):
    try:
        stories = request.stories[:10]
        result = await _create_issues_from_stories(stories)

        if result.errors:
            payload = JiraPublishErrorsResponse(errors=result.errors).model_dump()
            return JSONResponse(status_code=502, content=payload)

        return JiraPublishOkResponse()
    except RuntimeError as exc:
        logger.exception("Jira configuration error")
        return JSONResponse(status_code=500, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Failed to publish Jira issues")
        return JSONResponse(status_code=500, content={"error": str(exc)})

