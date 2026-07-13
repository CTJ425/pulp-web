"""Task 查詢(US-03);前端輪詢這裡,不阻塞等待。"""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_pulp
from ..pulp import PulpClient, PulpError
from ..schemas import TaskOut
from ..service import map_task

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATES = {"waiting", "skipped", "running", "completed", "failed", "canceled", "canceling"}


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    state: str | None = None,
    limit: int = Query(default=30, le=200),
    pulp: PulpClient = Depends(get_pulp),
) -> list[TaskOut]:
    if state and state not in VALID_STATES:
        raise HTTPException(422, f"state 必須是 {sorted(VALID_STATES)}")
    return [map_task(t) for t in await pulp.list_tasks(state=state, limit=limit)]


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, pulp: PulpClient = Depends(get_pulp)) -> TaskOut:
    try:
        return map_task(await pulp.get_task(task_id))
    except PulpError as exc:
        if exc.status == 404:
            raise HTTPException(404, f"task '{task_id}' not found") from exc
        raise
