"""Dashboard 總覽與管理操作(US-05 的 P1 子集:總覽 + orphan cleanup)。"""

import asyncio

from fastapi import APIRouter, Depends

from ..deps import get_pulp
from ..pulp import REPO_TYPES, PulpClient, task_id_from_href
from ..schemas import AcceptedTask, Overview

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/overview", response_model=Overview)
async def overview(pulp: PulpClient = Depends(get_pulp)) -> Overview:
    status, running, failed, *repo_lists = await asyncio.gather(
        pulp.status(),
        pulp.list_tasks(state="running", limit=100),
        pulp.list_tasks(state="failed", limit=100),
        *(pulp.list_all("repositories", t) for t in REPO_TYPES),
    )
    storage = status.get("storage") or {}
    return Overview(
        repo_counts={t: len(lst) for t, lst in zip(REPO_TYPES, repo_lists, strict=True)},
        running_tasks=len(running),
        failed_tasks=len(failed),
        online_workers=len(status.get("online_workers", [])),
        online_content_apps=len(status.get("online_content_apps", [])),
        storage_total=storage.get("total"),
        storage_used=storage.get("used"),
        storage_free=storage.get("free"),
        versions={v["component"]: v["version"] for v in status.get("versions", [])},
    )


@router.post("/orphan-cleanup", response_model=AcceptedTask, status_code=202)
async def orphan_cleanup(pulp: PulpClient = Depends(get_pulp)) -> AcceptedTask:
    return AcceptedTask(task=task_id_from_href(await pulp.orphan_cleanup()))
