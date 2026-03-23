
from sqlalchemy import text

#from db.session import get_async_engine


async def create_workspace() -> str:
    engine = get_async_engine()
    async with engine.begin() as conn:
        result = await conn.execute(text("insert into workspaces default values returning id"))
        workspace_id = result.scalar_one()
    await engine.dispose()
    return str(workspace_id)


async def get_workspace_state_snapshot(workspace_id: str):
    engine = get_async_engine()
    async with engine.connect() as conn:
        exists = await conn.execute(
            text("select 1 from workspaces where id = :workspace_id"),
            {"workspace_id": workspace_id},
        )
        if exists.first() is None:
            await engine.dispose()
            return None

        rows = await conn.execute(
            text(
                "select key, value_json from workspace_state where workspace_id = :workspace_id"
            ),
            {"workspace_id": workspace_id},
        )
        state = {row[0]: row[1] for row in rows.fetchall()}

    await engine.dispose()
    return {"workspace_id": workspace_id, "state": state}

