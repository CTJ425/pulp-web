"""VERIFICATION §1C.3(BFF/UI 層)之 API 部分;US-01~03 的整合驗證。"""

from conftest import wait_task

SEEDED = {"tiny-rpm", "tiny-deb", "tiny-hello"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_list_repos_contains_seeded(client):
    repos = client.get("/repos").json()
    assert SEEDED <= {r["name"] for r in repos}


def test_list_repos_type_filter(client):
    repos = client.get("/repos", params={"type": "rpm"}).json()
    assert all(r["type"] == "rpm" for r in repos)
    assert "tiny-rpm" in {r["name"] for r in repos}


def test_repo_detail_joined_fields(client):
    repo = client.get("/repos/tiny-rpm").json()
    assert repo["type"] == "rpm"
    assert repo["url"].startswith("http://fixtures/")
    assert repo["base_url"] and "/pulp/content/" in repo["base_url"]
    assert repo["latest_version"] >= 1


def test_repo_not_found_404(client):
    assert client.get("/repos/no-such-repo").status_code == 404


def test_create_repo_validation_422(client):
    resp = client.post("/repos", json={"name": "BAD NAME", "type": "rpm", "url": "http://x/"})
    assert resp.status_code == 422
    resp = client.post("/repos", json={"name": "c-x", "type": "container", "url": "http://x/"})
    assert resp.status_code == 422  # container 缺 upstream_name


def test_create_duplicate_409(client):
    resp = client.post(
        "/repos", json={"name": "tiny-rpm", "type": "rpm", "url": "http://fixtures/tiny-rpm/"}
    )
    assert resp.status_code == 409


def test_create_repo_then_sync_full_flow(client):
    """US-02 全流程:建立(202+task)→ 等 distribution 完成 → sync(202)→ 等完成。"""
    name = "apitest-rpm"
    create = client.post(
        "/repos",
        json={"name": name, "type": "rpm", "url": "http://fixtures/tiny-rpm/",
              "policy": "on_demand"},
    )
    if create.status_code == 409:
        pass  # 前次執行已建立;直接驗 sync
    else:
        assert create.status_code == 202
        wait_task(client, create.json()["task"])

    sync = client.post(f"/repos/{name}/sync")
    assert sync.status_code == 202
    wait_task(client, sync.json()["task"])

    repo = client.get(f"/repos/{name}").json()
    assert repo["latest_version"] >= 1


def test_sync_returns_202_and_task_completes(client):
    resp = client.post("/repos/tiny-rpm/sync")
    assert resp.status_code == 202
    task = wait_task(client, resp.json()["task"])
    assert task["state"] == "completed"


def test_client_config_rpm(client):
    resp = client.get("/repos/tiny-rpm/client-config")
    assert resp.status_code == 200
    assert "baseurl=" in resp.text and "/pulp/content/tiny-rpm/" in resp.text


def test_client_config_deb_uses_seeded_suite(client):
    text = client.get("/repos/tiny-deb/client-config").text
    assert "/pulp/content/tiny-deb/ tiny main" in text


def test_tasks_list_and_filter(client):
    tasks = client.get("/tasks", params={"limit": 5}).json()
    assert tasks and {"id", "name", "state"} <= tasks[0].keys()
    completed = client.get("/tasks", params={"state": "completed"}).json()
    assert all(t["state"] == "completed" for t in completed)
    assert client.get("/tasks", params={"state": "bogus"}).status_code == 422


def test_overview(client):
    data = client.get("/system/overview").json()
    assert data["repo_counts"]["rpm"] >= 1
    assert data["online_workers"] >= 1
    assert data["online_content_apps"] >= 1
    assert "core" in data["versions"]
