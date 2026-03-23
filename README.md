 # dev2-backend (API)
 
 FastAPI backend for requirements gathering + AI-assisted outputs (SRS chat, UI blueprint generation, UAT generation, Jira story drafting/publishing, and Figma-related utilities).
 
 ## Tech
 
 - **Framework**: FastAPI
 - **Server**: Uvicorn
 - **AI**: Google Gemini (via `google-genai` / `google-adk`)
 - **DB/Storage**: Supabase (service role key)
 - **Auth (optional)**: Clerk JWT verification
 - **Integrations (optional)**: Jira, Figma
 
 ## Prerequisites
 
 - Python 3.12+
 
 ## Setup
 
 1. Create and activate a virtual environment:
 
 ```bash
 # Windows (PowerShell)
 python -m venv venv
 .\venv\Scripts\Activate.ps1
 
 # Windows (CMD)
 python -m venv venv
 venv\Scripts\activate.bat
 
 # macOS / Linux
 python3 -m venv venv
 source venv/bin/activate
 ```
 
 2. Install dependencies:
 
 ```bash
 pip install -r requirements.txt
 ```
 
 3. Create a `.env` file.
 
 This codebase loads `.env` from the **repo root** (parent of this `api` folder). If your repo looks like:
 
 ```
 dev2-backend/
   .env
   api/
     main.py
 ```
 
 then your `.env` should live at `dev2-backend/.env`.
 
 ## Environment variables
 
 Minimum required to boot the API:
 
 - `API_KEY` (preferred) or `GEMINI_API_KEY`
 - `SUPABASE_URL`
 - `SUPABASE_SERVICE_ROLE_KEY`
 
 Optional / integration-specific:
 
 - `DISABLE_SSL_VERIFY` (`true`/`false`) — disables SSL verification for Supabase HTTP calls (intended for local Windows troubleshooting only)
 - `CLERK_JWKS_URL` — required if you call authenticated endpoints using `/auth/*`
 - `CLERK_ISSUER` — optional (enables issuer validation)
 - `JIRA_BASE_URL`
 - `JIRA_EMAIL`
 - `JIRA_API_TOKEN`
 - `JIRA_PROJECT_KEY`
 
 Example `.env`:
 
 ```bash
 # Gemini
 API_KEY=your_google_gemini_key
 
 # Supabase
 SUPABASE_URL=https://xxxx.supabase.co
 SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
 
 # Optional (local troubleshooting only)
 DISABLE_SSL_VERIFY=false
 
 # Optional: Clerk
 # CLERK_JWKS_URL=https://your-clerk-domain/.well-known/jwks.json
 # CLERK_ISSUER=https://clerk.your-domain
 
 # Optional: Jira
 # JIRA_BASE_URL=https://your-domain.atlassian.net
 # JIRA_EMAIL=you@company.com
 # JIRA_API_TOKEN=...
 # JIRA_PROJECT_KEY=ABC
 ```
 
 ## Run locally
 
 From the `api` folder:
 
 ```bash
 uvicorn main:app --reload --host 0.0.0.0 --port 8000
 ```
 
 Open Swagger UI:
 
 - http://localhost:8000/docs
 
 ## Routes / endpoints (high level)
 
 The API mounts multiple routers in `main.py` with different prefixes.
 
 ### Requirements + agent
 
 - `POST /chat` — streaming plain-text chat
 - `POST /agent/chat` — NDJSON streaming agent chat (tool-capable)
 - `POST /agent/generate-project` — generate a downloadable ZIP project
 - `POST /agent/save-local` — save generated output locally on the server machine
 - `GET /agent/state` — read current agent state for a session
 
 ### UI generation
 
 Prefix: `/ui`
 
 - `POST /ui/generate` — generate a UI blueprint from structured input
 - `POST /ui/screens/propose` — propose a list of screens
 - `POST /ui/screens/generate` — generate screens JSON/content
 
 ### UAT generation
 
 Prefix: `/api/uat`
 
 - `POST /api/uat/generate` — stream generated UAT test cases
 
 ### Jira integration
 
 Prefix: `/api/jira`
 
 - `POST /api/jira/issues/draft-from-srs` — draft Jira story JSON from an SRS text body
 - `POST /api/jira/issues/publish` — publish selected stories to Jira
 
 ### Workspaces
 
 Prefix: `/api/workspaces`
 
 - `POST /api/workspaces` — create a workspace
 - `GET /api/workspaces/{workspace_id}` — get a workspace snapshot
 
 ### Auth
 
 Prefix: `/auth`
 
 - `GET /auth/me` — verify bearer token and return current user payload
 
 ### Figma
 
 Prefix: `/figma`
 
 - `WS /figma/ws` — websocket for plugin connectivity
 - `POST /figma/push` — basic Figma connectivity/init endpoint
 - `POST /figma/generate-schema` — generate Figma JSON schema from inputs
 
 ### Health
 
 Prefix: `/api/health`
 
 - `GET /api/health/db` — database health check (may require additional DB config)
