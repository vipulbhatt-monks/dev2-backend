import os
from typing import Any, AsyncIterator, Dict, List, Optional
from dotenv import load_dotenv
from google import genai
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Standardize keys for SDKs
api_key = os.getenv("API_KEY")
if api_key:
    os.environ["GOOGLE_API_KEY"] = api_key
    os.environ["GEMINI_API_KEY"] = api_key


DEFAULT_MODEL = "gemini-3-flash-preview"
DEFAULT_TEMPERATURE = 0.2


def _get_api_key() -> Optional[str]:
    api_key = os.getenv("API_KEY")
    if api_key:
        return api_key
    return os.environ.get("GEMINI_API_KEY")


def get_client() -> genai.Client:
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("Missing API key. Set API_KEY or GEMINI_API_KEY.")
    return genai.Client(api_key=api_key)


async def generate_content_stream(
    *,
    contents: List[dict],
    system_instruction: str,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    tools: Optional[List[dict]] = None,
    tool_config: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[Any]:
    client = get_client()

    config: Dict[str, Any] = {
        "system_instruction": system_instruction,
        "temperature": temperature,
    }
    if tools is not None:
        config["tools"] = tools
    if tool_config is not None:
        config["tool_config"] = tool_config

    response = await client.aio.models.generate_content_stream(
        model=model,
        contents=contents,
        config=config,
    )
    async for chunk in response:
        yield chunk


async def generate_text(
    *,
    contents: List[dict],
    system_instruction: str,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    client = get_client()

    response = await client.aio.models.generate_content(
        model=model,
        contents=contents,
        config={
            "system_instruction": system_instruction,
            "temperature": temperature,
        },
    )

    # The SDK returns rich objects; .text is the most convenient.
    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError("Empty response from model")
    return text
