"""Repo/Task 的組裝邏輯;純函式為主,方便單元測試。"""

from typing import Any

from .pulp import task_id_from_href
from .schemas import Repo, RepoCreate, TaskOut


def build_remote_body(req: RepoCreate) -> dict[str, Any]:
    """依型態組出 Pulp remote create payload。"""
    body: dict[str, Any] = {"name": req.name, "url": req.url, "policy": req.policy}
    if req.type == "deb":
        body["distributions"] = req.deb_distributions or "stable"
        if req.deb_components:
            body["components"] = req.deb_components
        if req.deb_architectures:
            body["architectures"] = req.deb_architectures
    elif req.type == "container":
        if not req.upstream_name:
            raise ValueError("container repo 需要 upstream_name(如 library/nginx)")
        body["upstream_name"] = req.upstream_name
        if req.include_tags:
            body["include_tags"] = req.include_tags
        # container remote 不支援 on_demand 以外的… 支援 immediate/on_demand 皆可
    return body


def build_repository_body(req: RepoCreate, remote_href: str) -> dict[str, Any]:
    body: dict[str, Any] = {"name": req.name, "remote": remote_href}
    if req.type in ("rpm", "deb"):
        body["autopublish"] = True
    return body


def build_distribution_body(req: RepoCreate, repo_href: str) -> dict[str, Any]:
    return {
        "name": req.name,
        "base_path": req.base_path or req.name,
        "repository": repo_href,
    }


def join_repos(
    repo_type: str,
    repositories: list[dict],
    remotes: list[dict],
    distributions: list[dict],
) -> list[Repo]:
    """以名稱把 repository / remote / distribution 三張表拼成前端視圖。"""
    remotes_by_href = {r["pulp_href"]: r for r in remotes}
    dist_by_repo_href = {d["repository"]: d for d in distributions if d.get("repository")}
    out: list[Repo] = []
    for repo in repositories:
        remote = remotes_by_href.get(repo.get("remote") or "")
        dist = dist_by_repo_href.get(repo["pulp_href"])
        latest = repo.get("latest_version_href") or ""
        try:
            version = int(latest.rstrip("/").rsplit("/", 1)[-1])
        except ValueError:
            version = None
        out.append(
            Repo(
                name=repo["name"],
                type=repo_type,  # type: ignore[arg-type]
                url=remote.get("url") if remote else None,
                policy=remote.get("policy") if remote else None,
                base_path=dist.get("base_path") if dist else None,
                base_url=dist.get("base_url") if dist else None,
                latest_version=version,
                last_updated=repo.get("pulp_last_updated"),
                deb_distributions=remote.get("distributions") if remote else None,
                deb_components=remote.get("components") if remote else None,
            )
        )
    return out


def map_task(task: dict) -> TaskOut:
    error = task.get("error") or {}
    progress = [
        f"{pr.get('message', '')}: {pr.get('done', 0)}"
        + (f"/{pr['total']}" if pr.get("total") else "")
        for pr in task.get("progress_reports", [])
    ]
    return TaskOut(
        id=task_id_from_href(task["pulp_href"]),
        name=task.get("name", ""),
        state=task.get("state", "unknown"),
        started_at=task.get("started_at"),
        finished_at=task.get("finished_at"),
        error=error.get("description") if isinstance(error, dict) else str(error),
        progress=progress,
    )


def client_config(repo: Repo, mirror_url: str) -> str:
    """產生用戶端設定片段(US-01;SPEC §4)。"""
    host = mirror_url.rstrip("/")
    bare_host = host.split("://", 1)[-1]
    base_path = repo.base_path or repo.name
    if repo.type == "rpm":
        return (
            f"# /etc/yum.repos.d/lab-mirror-{repo.name}.repo\n"
            f"[lab-{repo.name}]\n"
            f"name=Lab Mirror - {repo.name}\n"
            f"baseurl={host}/pulp/content/{base_path}/\n"
            "enabled=1\n"
            "gpgcheck=0\n"
        )
    if repo.type == "deb":
        suite = (repo.deb_distributions or "stable").split()[0]
        components = repo.deb_components or "main"
        return (
            f"# /etc/apt/sources.list.d/lab-mirror-{repo.name}.list\n"
            f"deb [trusted=yes] {host}/pulp/content/{base_path}/ {suite} {components}\n"
        )
    return (
        f"# docker pull(直接指名)\n"
        f"docker pull {bare_host}/{base_path}:TAG\n"
        f"# 或於 /etc/docker/daemon.json 設 registry-mirrors 指向 {host}\n"
    )
