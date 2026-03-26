from fastapi import APIRouter, Depends

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from services.clerk import verify_token

from typing import Any, Dict

from db.crud import ensure_user



router = APIRouter(prefix="/auth", tags=["Auth"])

security = HTTPBearer()



async def get_current_user(

    credentials: HTTPAuthorizationCredentials = Depends(security)

) -> Dict[str, Any]:

    payload = await verify_token(credentials.credentials)

    user_row = ensure_user(
        clerk_user_id=payload["sub"],
    )

    return {"payload": payload, "user": user_row}


@router.get("/me")

async def get_me(user_data: Dict[str, Any] = Depends(get_current_user)):

    return user_data