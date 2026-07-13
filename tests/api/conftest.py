"""API 整合測試(make test-api):打 dev 環境的 BFF(經 nginx)。

前置:make dev && make seed(tiny-rpm / tiny-deb / tiny-hello 已存在)。
"""

import os
import time

import httpx
import pytest

BASE = os.environ.get("BFF_BASE_URL", "http://localhost:8080/api/v1")


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE, timeout=30.0) as c:
        # 環境未起時直接讓整組測試 fail-fast,而不是每筆各噴一次
        resp = c.get("/health")
        assert resp.status_code == 200, "BFF 不可達;先跑 make dev"
        yield c


def wait_task(client: httpx.Client, task_id: str, timeout: float = 120.0) -> dict:
    """輪詢 task 至終態;完成回傳 task dict,逾時或失敗直接 fail。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = client.get(f"/tasks/{task_id}").json()
        if task["state"] in ("completed", "failed", "canceled"):
            assert task["state"] == "completed", f"task 失敗:{task.get('error')}"
            return task
        time.sleep(1)
    pytest.fail(f"task {task_id} 超過 {timeout}s 未完成")
