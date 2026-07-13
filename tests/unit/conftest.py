import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("PULP_PASSWORD", "test-only")
os.environ.setdefault("MIRROR_URL", "https://mirror.lab.local")

from app.config import Settings  # noqa: E402
from app.deps import get_pulp, get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.pulp import PulpError  # noqa: E402

TASKS_BASE = "/pulp/api/v3/tasks"


class FakePulp:
    """記錄呼叫、回傳可注入資料的 Pulp 替身。"""

    def __init__(self):
        self.repositories: dict[str, list[dict]] = {"rpm": [], "deb": [], "container": []}
        self.remotes: dict[str, list[dict]] = {"rpm": [], "deb": [], "container": []}
        self.distributions: dict[str, list[dict]] = {"rpm": [], "deb": [], "container": []}
        self.tasks: list[dict] = []
        self.calls: list[tuple] = []
        self.status_payload = {
            "online_workers": [{}],
            "online_content_apps": [{}],
            "versions": [{"component": "core", "version": "3.114.0"}],
            "storage": {"total": 100, "used": 40, "free": 60},
        }

    def add_repo(self, repo_type: str, name: str, *, version: int = 1, policy: str = "on_demand",
                 url: str = "http://fixtures/x/", **remote_extra) -> None:
        remote_href = f"/pulp/api/v3/remotes/{repo_type}/x/{name}/"
        repo_href = f"/pulp/api/v3/repositories/{repo_type}/x/{name}/"
        self.remotes[repo_type].append(
            {"pulp_href": remote_href, "name": name, "url": url, "policy": policy, **remote_extra}
        )
        self.repositories[repo_type].append(
            {
                "pulp_href": repo_href,
                "name": name,
                "remote": remote_href,
                "latest_version_href": f"{repo_href}versions/{version}/",
                "pulp_last_updated": "2026-07-13T00:00:00Z",
            }
        )
        self.distributions[repo_type].append(
            {
                "pulp_href": f"/pulp/api/v3/distributions/{repo_type}/x/{name}/",
                "name": name,
                "repository": repo_href,
                "base_path": name,
                "base_url": f"http://localhost:8080/pulp/content/{name}/",
            }
        )

    # ---- PulpClient 介面 ----

    async def list_all(self, kind: str, repo_type: str, **params):
        data = getattr(self, kind)[repo_type]
        if "name" in params:
            data = [d for d in data if d["name"] == params["name"]]
        return data

    async def create_remote(self, repo_type, body):
        self.calls.append(("create_remote", repo_type, body))
        return {"pulp_href": f"/pulp/api/v3/remotes/{repo_type}/x/new/", **body}

    async def create_repository(self, repo_type, body):
        self.calls.append(("create_repository", repo_type, body))
        return {"pulp_href": f"/pulp/api/v3/repositories/{repo_type}/x/new/", **body}

    async def create_distribution(self, repo_type, body):
        self.calls.append(("create_distribution", repo_type, body))
        return f"{TASKS_BASE}/11111111-1111-1111-1111-111111111111/"

    async def sync(self, repo_href, body=None):
        self.calls.append(("sync", repo_href))
        return f"{TASKS_BASE}/22222222-2222-2222-2222-222222222222/"

    async def orphan_cleanup(self):
        return f"{TASKS_BASE}/33333333-3333-3333-3333-333333333333/"

    async def list_tasks(self, state=None, limit=30):
        tasks = self.tasks
        if state:
            tasks = [t for t in tasks if t["state"] == state]
        return tasks[:limit]

    async def get_task(self, task_id):
        for t in self.tasks:
            if t["pulp_href"].rstrip("/").endswith(task_id):
                return t
        raise PulpError(404, "Not found.")

    async def status(self):
        return self.status_payload


@pytest.fixture()
def fake_pulp() -> FakePulp:
    return FakePulp()


@pytest.fixture()
def client(fake_pulp) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_pulp] = lambda: fake_pulp
    app.dependency_overrides[get_settings] = lambda: Settings()
    with TestClient(app) as c:
        yield c
