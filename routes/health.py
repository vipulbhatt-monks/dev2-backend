from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

#from db.session import get_async_engine, get_database_url, get_engine, is_async_database_url


router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/db")
async def db_health_check():
    database_url = get_database_url()
    if not is_async_database_url(database_url):
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "DATABASE_URL must use asyncpg (postgresql+asyncpg://...) because psycopg2 is not installed.",
            },
        )

    engine = get_async_engine()
    async with engine.connect() as conn:
        await conn.execute(text("select 1"))
    await engine.dispose()
    return {"ok": True, "driver": "asyncpg"}
