"""Pulp REST API 的薄封裝。

路徑慣例(pulpcore /pulp/api/v3/):
  repositories/{rpm/rpm | deb/apt | container/container}/
  remotes/…、distributions/… 同型態對應。
非同步操作(sync、distribution create)回傳 task href,由呼叫端轉成 202。
"""

from typing import Any

import httpx

# BFF repo type → Pulp plugin 路徑片段
PLUGIN_PATH = {
    "rpm": "rpm/rpm",
    "deb": "deb/apt",
    "container": "container/container",
}
REPO_TYPES = tuple(PLUGIN_PATH)

API = "/pulp/api/v3"


def task_id_from_href(href: str) -> str:
    """/pulp/api/v3/tasks/<uuid>/ → <uuid>"""
    return href.rstrip("/").rsplit("/", 1)[-1]


class PulpError(Exception):
    """Pulp 回應非 2xx;status/detail 供 router 轉成 HTTP 錯誤。"""

    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"pulp returned {status}: {detail}")


class PulpClient:
    def __init__(self, base_url: str, username: str, password: str):
        self._client = httpx.AsyncClient(
            base_url=base_url, auth=(username, password), timeout=30.0
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text
            raise PulpError(resp.status_code, detail)
        return resp.json() if resp.content else None

    async def get(self, path: str, **params) -> Any:
        return await self._request("GET", path, params=params or None)

    async def post(self, path: str, body: dict) -> Any:
        return await self._request("POST", path, json=body)

    # ---- 平台 ----

    async def status(self) -> dict:
        return await self.get(f"{API}/status/")

    # ---- 各型態資源列表(回傳 results list) ----

    async def list_all(self, kind: str, repo_type: str, **params) -> list[dict]:
        """kind ∈ repositories/remotes/distributions;自動翻頁蒐集全部。"""
        path = f"{API}/{kind}/{PLUGIN_PATH[repo_type]}/"
        results: list[dict] = []
        page = await self.get(path, limit=100, **params)
        results.extend(page["results"])
        while page.get("next"):
            page = await self.get(page["next"])
            results.extend(page["results"])
        return results

    # ---- 建立(remote/repository 同步回傳、distribution 回傳 task) ----

    async def create_remote(self, repo_type: str, body: dict) -> dict:
        return await self.post(f"{API}/remotes/{PLUGIN_PATH[repo_type]}/", body)

    async def create_repository(self, repo_type: str, body: dict) -> dict:
        return await self.post(f"{API}/repositories/{PLUGIN_PATH[repo_type]}/", body)

    async def create_distribution(self, repo_type: str, body: dict) -> str:
        """distribution create 是非同步 → 回傳 task href。"""
        resp = await self.post(f"{API}/distributions/{PLUGIN_PATH[repo_type]}/", body)
        return resp["task"]

    # ---- 非同步操作 ----

    async def sync(self, repo_href: str, body: dict | None = None) -> str:
        resp = await self.post(f"{repo_href}sync/", body or {})
        return resp["task"]

    async def orphan_cleanup(self) -> str:
        resp = await self.post(f"{API}/orphans/cleanup/", {})
        return resp["task"]

    # ---- Tasks ----

    async def list_tasks(self, state: str | None = None, limit: int = 30) -> list[dict]:
        params: dict[str, Any] = {"ordering": "-pulp_created", "limit": limit}
        if state:
            params["state"] = state
        page = await self.get(f"{API}/tasks/", **params)
        return page["results"]

    async def get_task(self, task_id: str) -> dict:
        return await self.get(f"{API}/tasks/{task_id}/")
