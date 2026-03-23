from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from services.clerk import verify_token
from models.user import CurrentUser

router = APIRouter(prefix="/auth", tags=["Auth"])
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> CurrentUser:
    payload = await verify_token(credentials.credentials)
    return CurrentUser(
        user_id=payload["sub"],
        session_id=payload.get("sid")
    )


@router.get("/me")
async def get_me(user: CurrentUser = Depends(get_current_user)):
    return user