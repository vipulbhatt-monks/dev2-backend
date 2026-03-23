<<<<<<< HEAD
# MONKS API (Requirements + UI Generation)

FastAPI backend powered by Google Gemini AI.

## Features

- **Requirements Chat**: Streaming chat endpoint
- **Requirements Agent**: Tool-driven SRS (Software Requirements Specification) generation
- **Project Export**: Export requirements as downloadable ZIP files
- **UI Blueprint Generation**: Generate a UI wireframe blueprint JSON from:
  - Structured fields (projectName/userRoles/features/constraints)
  - Full requirements document (requirementsDoc)

## Setup

1. Install dependencies:
=======
# MONKS Requirements API

A FastAPI-based requirements gathering system powered by Google Gemini AI.

## Features

- **Chat Interface**: Standard chat with Gemini AI
- **Requirements Agent**: Structured SRS (Software Requirements Specification) generation
- **Project Generation**: Export requirements as downloadable ZIP files
- **Local Save**: Save requirements directly to local filesystem

## Setup

1. **Install dependencies**:
>>>>>>> 559916e (Initial commit)
   ```bash
   pip install -r requirements.txt
   ```

<<<<<<< HEAD
2. Set environment variables (one of these is required):
   - `API_KEY` (preferred)
   - or `GEMINI_API_KEY`

   Example `.env`:
   ```bash
   API_KEY=your_key_here
   ```

3. Run the server:
=======
2. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env and add your Gemini API key
   ```

3. **Run the server**:
>>>>>>> 559916e (Initial commit)
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

<<<<<<< HEAD
4. Open Swagger UI:
   - http://localhost:8000/docs

## API Base Path Notes

In `main.py`, routers are mounted like this:

- Requirements router: included directly (no `/api` prefix)
- UI router: included under `/api` prefix

So:

- Requirements endpoints are `/<...>`
- UI endpoints are `/api/ui/<...>`

## Requirements Endpoints

### POST `/chat`

Standard chat endpoint with streaming responses.

### POST `/agent/chat`

Requirements agent chat endpoint (NDJSON streaming) with tool support.

### POST `/agent/generate-project`

Generate a downloadable ZIP file with requirements.

### POST `/agent/save-local`

Save requirements locally (and attempt to open in Windsurf).

## UI Generation Endpoints

### POST `/api/ui/generate` (Structured mode)

Generate UI blueprint from structured fields.

#### Request

```json
{
  "projectName": "Monks",
  "userRoles": ["Admin", "Customer"],
  "features": ["Login", "Browse products", "Checkout"],
  "constraints": ["Mobile-first", "Fast load"]
}
```

### POST `/api/ui/generate-from-doc` (Doc mode)

Generate UI blueprint from a full requirements document.

#### Request

```json
{
  "projectName": "Monks",
  "requirementsDoc": "# Monks SRS\n\n## Users\n- Admin\n- Customer\n\n## Features\n- Login\n- Checkout\n"
}
```

### POST `/api/ui/generate-code` (HTML/CSS code from blueprint)

Generate HTML and CSS for each screen using an existing UI blueprint.

#### Request

```json
{
  "projectName": "Monks",
  "blueprint": {
    "screens": [
      {
        "name": "Login",
        "components": ["Email input", "Password input", "Login button"]
      }
    ],
    "userFlows": ["User opens app → Login"]
  }
}
```

#### Response (example)

```json
{
  "screens": [
    {
      "name": "Login",
      "html": "<div class=\"screen-login\">...</div>",
      "css": ".screen-login { ... }"
    }
  ],
  "globalCss": "/* optional shared styles */"
}
```

## UI Blueprint Response Format

Both UI blueprint generation endpoints return the same shape:

```json
{
  "screens": [
    {
      "name": "Login",
      "components": ["Email input", "Password input", "Login button"]
    }
  ],
  "userFlows": [
    "User opens app → Login → Home → Browse → Add to cart → Checkout"
  ]
}
```

## Error Format (UI endpoints)

On failures, UI endpoints return:

```json
{
  "error": "UI blueprint generation failed",
  "details": "..."
}
```

- `502`: AI/model/validation failure
- `500`: Internal Server Error (no stack traces exposed)

## Environment Variables

- `API_KEY`: Google Gemini API key (preferred)
- `GEMINI_API_KEY`: fallback API key name (also supported)

## Quick Test (cURL)

### Structured

```bash
curl -X POST "http://localhost:8000/api/ui/generate" \
  -H "Content-Type: application/json" \
  -d "{\"projectName\":\"Monks\",\"userRoles\":[\"Admin\"],\"features\":[\"Login\",\"Checkout\"],\"constraints\":[\"Mobile-first\"]}"
```

### Doc

```bash
curl -X POST "http://localhost:8000/api/ui/generate-from-doc" \
  -H "Content-Type: application/json" \
  -d "{\"projectName\":\"Monks\",\"requirementsDoc\":\"Build a task manager app. Users can create/edit/complete tasks.\"}"
```

### Generate HTML/CSS code from blueprint

```bash
curl -X POST "http://localhost:8000/api/ui/generate-code" \
  -H "Content-Type: application/json" \
  -d "{\"projectName\":\"Monks\",\"blueprint\":{\"screens\":[{\"name\":\"Login\",\"components\":[\"Email input\",\"Password input\",\"Login button\"]}],\"userFlows\":[\"User opens app → Login\"]}}"
```
=======
## API Endpoints

### POST `/chat`
Standard chat endpoint with streaming responses.

### POST `/agent/chat`
Requirements agent chat endpoint with tool support.

### POST `/agent/generate-project`
Generate a downloadable ZIP file with requirements.

### POST `/agent/save-local`
Save requirements locally and attempt to open in Windsurf.

## Usage

1. Start the server
2. Use the requirements agent by sending messages to `/agent/chat`
3. The agent will guide you through creating a complete SRS
4. Export your requirements using `/agent/generate-project` or `/agent/save-local`

## Environment Variables

- `GEMINI_API_KEY`: Your Google Gemini API key (required)
- `FASTAPI_HOST`: Server host (default: 0.0.0.0)
- `FASTAPI_PORT`: Server port (default: 8000)
- `FASTAPI_DEBUG`: Debug mode (default: true)
>>>>>>> 559916e (Initial commit)
