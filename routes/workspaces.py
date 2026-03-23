from fastapi import APIRouter, HTTPException

from db.workspaces import create_workspace, get_workspace_state_snapshot


router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.post("")
async def create_workspace_endpoint():
    workspace_id = await create_workspace()
    return {"workspace_id": workspace_id}


@router.get("/{workspace_id}")
async def get_workspace_endpoint(workspace_id: str):
    snapshot = await get_workspace_state_snapshot(workspace_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return snapshot
