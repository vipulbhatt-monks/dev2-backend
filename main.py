from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
from pathlib import Path

# Load .env from project root (parent of 'api' folder)
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

# Ensure standardized environment variables for all Google SDKs
api_key = os.getenv("API_KEY")
if api_key:
    os.environ["GOOGLE_API_KEY"] = api_key
    os.environ["GEMINI_API_KEY"] = api_key

from routes.requirements import router as requirements_router
from routes.ui_generation import router as ui_router
from routes.uat import router as uat_router
from routes.jira import router as jira_router
from routes.figma_export import router as figma_router
from routes.health import router as health_router
from routes.workspaces import router as workspaces_router
from routes.auth import router as auth_router



app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(requirements_router)
app.include_router(ui_router)
app.include_router(uat_router)
app.include_router(figma_router)
app.include_router(jira_router)
app.include_router(health_router)
app.include_router(workspaces_router)
app.include_router(auth_router)
