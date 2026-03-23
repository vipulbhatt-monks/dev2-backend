import base64
import os
from typing import Any, Dict, Optional

import httpx


class JiraServiceError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        jira_response: Optional[Any] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.jira_response = jira_response


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _basic_auth_header(email: str, api_token: str) -> str:
    token = f"{email}:{api_token}".encode("utf-8")
    encoded = base64.b64encode(token).decode("utf-8")
    return f"Basic {encoded}"


def _to_adf(text: str) -> Dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text or ""}],
            }
        ],
    }


async def create_story_issue(
    *,
    summary: str,
    description: str,
    issue_type: Optional[str] = None,
    labels: Optional[list[str]] = None,
) -> str:
    base_url = _require_env("JIRA_BASE_URL").rstrip("/")
    email = _require_env("JIRA_EMAIL")
    api_token = _require_env("JIRA_API_TOKEN")
    project_key = _require_env("JIRA_PROJECT_KEY")

    url = f"{base_url}/rest/api/3/issue"
    fields: Dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary,
        "description": _to_adf(description),
    }

    if issue_type:
        fields["issuetype"] = {"name": issue_type}
    else:
        fields["issuetype"] = {"id": "10004"}

    if labels:
        fields["labels"] = labels

    payload: Dict[str, Any] = {"fields": fields}

    headers = {
        "Authorization": _basic_auth_header(email, api_token),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise JiraServiceError(f"Network error calling Jira: {exc}") from exc

    if 200 <= resp.status_code < 300:
        data = resp.json()
        key = data.get("key")
        if not key:
            raise JiraServiceError(
                "Jira response missing issue key",
                status_code=resp.status_code,
                jira_response=data,
            )
        return key

    try:
        body: Any = resp.json()
    except Exception:
        body = resp.text

    message = "Jira issue creation failed"
    if isinstance(body, dict):
        err_msgs = body.get("errorMessages")
        if isinstance(err_msgs, list) and err_msgs:
            message = "; ".join([str(m) for m in err_msgs])

    raise JiraServiceError(message, status_code=resp.status_code, jira_response=body)
