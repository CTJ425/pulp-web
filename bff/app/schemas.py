"""BFF 對前端的資料模型(SPEC §3.7);repo 以名稱為識別,不外露 Pulp href。"""

from typing import Literal

from pydantic import BaseModel, Field

RepoType = Literal["rpm", "deb", "container"]


class Repo(BaseModel):
    name: str
    type: RepoType
    url: str | None = None  # 上游 URL(remote)
    policy: str | None = None
    base_path: str | None = None
    base_url: str | None = None  # 用戶端實際取用位址
    latest_version: int | None = None
    last_updated: str | None = None
    # deb 專用(client-config 需要 suite/component)
    deb_distributions: str | None = None
    deb_components: str | None = None


class RepoCreate(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=64)
    type: RepoType
    url: str
    policy: Literal["immediate", "on_demand"] = "on_demand"
    base_path: str | None = None  # 預設 = name
    # deb 專用
    deb_distributions: str | None = None  # 空白分隔,如 "noble"
    deb_components: str | None = None  # 如 "main"
    deb_architectures: str | None = None  # 如 "amd64"
    # container 專用
    upstream_name: str | None = None  # 如 "library/nginx"
    include_tags: list[str] | None = None


class TaskOut(BaseModel):
    id: str
    name: str
    state: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    progress: list[str] = []


class AcceptedTask(BaseModel):
    """202 回應:非同步操作已送出,前端輪詢 /tasks/{id}。"""

    task: str


class Overview(BaseModel):
    repo_counts: dict[str, int]
    running_tasks: int
    failed_tasks: int
    online_workers: int
    online_content_apps: int
    storage_total: int | None = None
    storage_used: int | None = None
    storage_free: int | None = None
    versions: dict[str, str] = {}
