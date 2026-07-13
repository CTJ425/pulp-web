"""Repo CRUD 與同步(US-01、US-02);{name} 為全域唯一識別(SPEC §3.7)。"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from .. import service
from ..deps import get_pulp, get_settings
from ..pulp import REPO_TYPES, PulpClient, task_id_from_href
from ..schemas import AcceptedTask, Repo, RepoCreate

router = APIRouter(prefix="/repos", tags=["repos"])


async def _repos_of_type(pulp: PulpClient, repo_type: str) -> list[Repo]:
    repositories, remotes, distributions = await asyncio.gather(
        pulp.list_all("repositories", repo_type),
        pulp.list_all("remotes", repo_type),
        pulp.list_all("distributions", repo_type),
    )
    return service.join_repos(repo_type, repositories, remotes, distributions)


async def _all_repos(pulp: PulpClient, repo_type: str | None = None) -> list[Repo]:
    types = [repo_type] if repo_type else list(REPO_TYPES)
    groups = await asyncio.gather(*(_repos_of_type(pulp, t) for t in types))
    return [repo for group in groups for repo in group]


async def _find_repo(pulp: PulpClient, name: str) -> Repo:
    for repo in await _all_repos(pulp):
        if repo.name == name:
            return repo
    raise HTTPException(404, f"repo '{name}' not found")


@router.get("", response_model=list[Repo])
async def list_repos(
    type: str | None = None, pulp: PulpClient = Depends(get_pulp)
) -> list[Repo]:
    if type and type not in REPO_TYPES:
        raise HTTPException(422, f"type 必須是 {REPO_TYPES}")
    return await _all_repos(pulp, type)


@router.post("", response_model=AcceptedTask, status_code=202)
async def create_repo(req: RepoCreate, pulp: PulpClient = Depends(get_pulp)) -> AcceptedTask:
    # 名稱全域唯一(跨三種型態)
    existing = {r.name for r in await _all_repos(pulp)}
    if req.name in existing:
        raise HTTPException(409, f"repo '{req.name}' 已存在")
    try:
        remote_body = service.build_remote_body(req)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    remote = await pulp.create_remote(req.type, remote_body)
    repository = await pulp.create_repository(
        req.type, service.build_repository_body(req, remote["pulp_href"])
    )
    task_href = await pulp.create_distribution(
        req.type, service.build_distribution_body(req, repository["pulp_href"])
    )
    return AcceptedTask(task=task_id_from_href(task_href))


@router.get("/{name}", response_model=Repo)
async def get_repo(name: str, pulp: PulpClient = Depends(get_pulp)) -> Repo:
    return await _find_repo(pulp, name)


@router.post("/{name}/sync", response_model=AcceptedTask, status_code=202)
async def sync_repo(name: str, pulp: PulpClient = Depends(get_pulp)) -> AcceptedTask:
    repo = await _find_repo(pulp, name)
    repositories = await pulp.list_all("repositories", repo.type, name=name)
    if not repositories:
        raise HTTPException(404, f"repo '{name}' not found")
    task_href = await pulp.sync(repositories[0]["pulp_href"])
    return AcceptedTask(task=task_id_from_href(task_href))


@router.get("/{name}/client-config", response_class=PlainTextResponse)
async def repo_client_config(
    name: str,
    pulp: PulpClient = Depends(get_pulp),
    settings=Depends(get_settings),
) -> str:
    repo = await _find_repo(pulp, name)
    return service.client_config(repo, settings.mirror_url)
