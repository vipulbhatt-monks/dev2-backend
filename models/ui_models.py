from pydantic import BaseModel, Field
from typing import List, Optional


class UIGenerateRequest(BaseModel):
    projectName: Optional[str] = None
    userRoles: List[str] = Field(default_factory=list)
    features: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)


class UIScreen(BaseModel):
    name: str
    components: List[str]


class UIBlueprintResponse(BaseModel):
    screens: List[UIScreen]
    userFlows: List[str]


class UIBlueprintError(BaseModel):
    error: str
    details: Optional[str] = None

class ScreenProposalRequest(BaseModel):
    prompt: str
    file_content: str | None = None
    file_type: str | None = None

class ProposedScreen(BaseModel):
    id: str
    title: str
    description: str

class UIScreenCode(BaseModel):
    name: str
    html: str
    css: str

class ScreenProposalResponse(BaseModel):
    appName: str
    screens: List[ProposedScreen]

class ScreenGenerateRequest(BaseModel):
    appName: str
    screens: List[ProposedScreen]
    prompt: str
    file_content: str | None = None
    file_type: str | None = None

class UIGenerateCodeRequest(BaseModel):
    projectName: Optional[str] = None
    blueprint: UIBlueprintResponse


class UIGenerateCodeResponse(BaseModel):
    screens: List[UIScreenCode]
    globalCss: Optional[str] = None
