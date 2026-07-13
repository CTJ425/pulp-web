TASK_HREF = "/pulp/api/v3/tasks/aaaaaaaa-0000-0000-0000-000000000000/"


def test_health(client, fake_pulp):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_list_repos_joined(client, fake_pulp):
    fake_pulp.add_repo("rpm", "tiny-rpm", version=3)
    fake_pulp.add_repo("deb", "tiny-deb", distributions="tiny", components="main")
    resp = client.get("/api/v1/repos")
    assert resp.status_code == 200
    repos = {r["name"]: r for r in resp.json()}
    assert repos["tiny-rpm"]["latest_version"] == 3
    assert repos["tiny-rpm"]["base_url"].endswith("/pulp/content/tiny-rpm/")
    assert repos["tiny-deb"]["type"] == "deb"


def test_list_repos_type_filter_and_validation(client, fake_pulp):
    fake_pulp.add_repo("rpm", "a")
    fake_pulp.add_repo("deb", "b")
    only_rpm = client.get("/api/v1/repos", params={"type": "rpm"}).json()
    assert [r["name"] for r in only_rpm] == ["a"]
    assert client.get("/api/v1/repos", params={"type": "npm"}).status_code == 422


def test_create_repo_returns_202_with_task(client, fake_pulp):
    resp = client.post("/api/v1/repos", json={
        "name": "new-rpm", "type": "rpm", "url": "http://fixtures/tiny-rpm/",
    })
    assert resp.status_code == 202
    assert resp.json()["task"] == "11111111-1111-1111-1111-111111111111"
    kinds = [c[0] for c in fake_pulp.calls]
    assert kinds == ["create_remote", "create_repository", "create_distribution"]


def test_create_repo_duplicate_name_conflicts_across_types(client, fake_pulp):
    fake_pulp.add_repo("deb", "taken")
    resp = client.post("/api/v1/repos", json={
        "name": "taken", "type": "rpm", "url": "http://x/",
    })
    assert resp.status_code == 409


def test_create_repo_invalid_name_rejected(client, fake_pulp):
    resp = client.post("/api/v1/repos", json={
        "name": "Bad Name!", "type": "rpm", "url": "http://x/",
    })
    assert resp.status_code == 422


def test_create_container_repo_requires_upstream_name(client, fake_pulp):
    resp = client.post("/api/v1/repos", json={
        "name": "c1", "type": "container", "url": "http://up:5000",
    })
    assert resp.status_code == 422


def test_sync_returns_202(client, fake_pulp):
    fake_pulp.add_repo("rpm", "tiny-rpm")
    resp = client.post("/api/v1/repos/tiny-rpm/sync")
    assert resp.status_code == 202
    assert resp.json()["task"] == "22222222-2222-2222-2222-222222222222"


def test_sync_unknown_repo_404(client, fake_pulp):
    assert client.post("/api/v1/repos/nope/sync").status_code == 404


def test_client_config_endpoint_plaintext(client, fake_pulp):
    fake_pulp.add_repo("rpm", "tiny-rpm")
    resp = client.get("/api/v1/repos/tiny-rpm/client-config")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "baseurl=" in resp.text


def test_tasks_list_filter_and_validation(client, fake_pulp):
    fake_pulp.tasks = [
        {"pulp_href": TASK_HREF, "name": "sync", "state": "running"},
        {"pulp_href": TASK_HREF, "name": "sync", "state": "failed",
         "error": {"description": "x"}},
    ]
    running = client.get("/api/v1/tasks", params={"state": "running"}).json()
    assert len(running) == 1 and running[0]["state"] == "running"
    assert client.get("/api/v1/tasks", params={"state": "bogus"}).status_code == 422


def test_get_task_found_and_missing(client, fake_pulp):
    fake_pulp.tasks = [{"pulp_href": TASK_HREF, "name": "sync", "state": "completed"}]
    ok = client.get("/api/v1/tasks/aaaaaaaa-0000-0000-0000-000000000000")
    assert ok.status_code == 200 and ok.json()["state"] == "completed"
    assert client.get("/api/v1/tasks/deadbeef-0000-0000-0000-000000000000").status_code == 404


def test_overview_counts(client, fake_pulp):
    fake_pulp.add_repo("rpm", "a")
    fake_pulp.add_repo("rpm", "b")
    fake_pulp.add_repo("container", "c")
    fake_pulp.tasks = [{"pulp_href": TASK_HREF, "name": "t", "state": "failed",
                        "error": {"description": "x"}}]
    data = client.get("/api/v1/system/overview").json()
    assert data["repo_counts"] == {"rpm": 2, "deb": 0, "container": 1}
    assert data["failed_tasks"] == 1
    assert data["storage_used"] == 40
    assert data["versions"]["core"] == "3.114.0"


def test_orphan_cleanup_202(client, fake_pulp):
    resp = client.post("/api/v1/system/orphan-cleanup")
    assert resp.status_code == 202
