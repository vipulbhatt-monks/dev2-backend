from pydantic import BaseModel, Field
from typing import Any, List, Optional


class JiraStory(BaseModel):
    summary: str
    description: str
    issue_type: Optional[str] = None
    labels: Optional[List[str]] = None


class JiraDraftStory(JiraStory):
    id: str


class JiraDraftStoriesResponse(BaseModel):
    stories: List[JiraDraftStory]


class JiraPublishStoriesRequest(BaseModel):
    stories: List[JiraStory]


class JiraPublishOkResponse(BaseModel):
    ok: bool = True


class JiraIssueCreateError(BaseModel):
    index: int
    summary: Optional[str] = None
    error: str
    status_code: Optional[int] = None
    jira_response: Optional[Any] = None


class JiraPublishErrorsResponse(BaseModel):
    errors: List[JiraIssueCreateError] = Field(default_factory=list)


class JiraCreateIssuesResponse(BaseModel):
    created_issues: List[str]
    errors: List[JiraIssueCreateError] = Field(default_factory=list)
