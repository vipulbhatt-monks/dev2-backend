import os
import time
from typing import Any, Optional

import httpx
import jwt
from fastapi import HTTPException
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

_jwks_cache: Optional[dict[str, Any]] = None
_jwks_cache_fetched_at: float = 0.0
_JWKS_CACHE_TTL_SECONDS = 600


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def get_jwks(*, force_refresh: bool = False) -> dict[str, Any]:
    global _jwks_cache
    global _jwks_cache_fetched_at

    jwks_url = _require_env("CLERK_JWKS_URL")
    now = time.time()
    cache_is_valid = _jwks_cache is not None and (now - _jwks_cache_fetched_at) < _JWKS_CACHE_TTL_SECONDS

    if force_refresh or not cache_is_valid:
        disable_ssl_verify = os.getenv("DISABLE_SSL_VERIFY", "false").lower() == "true"
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            verify=(not disable_ssl_verify),
        ) as client:
            res = await client.get(jwks_url)
            res.raise_for_status()
            _jwks_cache = res.json()
            _jwks_cache_fetched_at = now

    return _jwks_cache or {}


async def verify_token(token: str):
    try:
        header = jwt.get_unverified_header(token)

        async def _decode_with_jwks(jwks_dict: dict[str, Any]):
            public_keys = jwt.PyJWKSet.from_dict(jwks_dict)
            key = next(k for k in public_keys.keys if k.key_id == header["kid"])

            issuer = os.getenv("CLERK_ISSUER")
            options = {"verify_aud": False}

            decode_kwargs: dict[str, Any] = {
                "algorithms": ["RS256"],
                "options": options,
            }

            if issuer:
                decode_kwargs["issuer"] = issuer
                options["verify_iss"] = True
            else:
                options["verify_iss"] = False

            return jwt.decode(token, key.key, **decode_kwargs)

        try:
            return await _decode_with_jwks(await get_jwks())
        except StopIteration:
            return await _decode_with_jwks(await get_jwks(force_refresh=True))

    except StopIteration:
        raise HTTPException(status_code=401, detail="Unknown token key")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")