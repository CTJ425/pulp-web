import pytest

from app import service
from app.schemas import Repo, RepoCreate


def test_build_remote_body_rpm():
    req = RepoCreate(name="r1", type="rpm", url="http://up/r/", policy="immediate")
    assert service.build_remote_body(req) == {
        "name": "r1",
        "url": "http://up/r/",
        "policy": "immediate",
    }


def test_build_remote_body_deb_defaults_and_fields():
    req = RepoCreate(
        name="d1", type="deb", url="http://up/d/",
        deb_distributions="noble", deb_components="main", deb_architectures="amd64",
    )
    body = service.build_remote_body(req)
    assert body["distributions"] == "noble"
    assert body["components"] == "main"
    assert body["architectures"] == "amd64"
    # 未指定 suite 時給安全預設,避免 Pulp 422
    assert service.build_remote_body(
        RepoCreate(name="d2", type="deb", url="http://up/d/")
    )["distributions"] == "stable"


def test_build_remote_body_container_requires_upstream_name():
    req = RepoCreate(name="c1", type="container", url="http://up:5000")
    with pytest.raises(ValueError):
        service.build_remote_body(req)
    ok = service.build_remote_body(
        RepoCreate(name="c1", type="container", url="http://up:5000",
                   upstream_name="tiny/hello", include_tags=["latest"])
    )
    assert ok["upstream_name"] == "tiny/hello"
    assert ok["include_tags"] == ["latest"]


def test_build_repository_body_autopublish_only_for_rpm_deb():
    rpm = RepoCreate(name="a", type="rpm", url="u")
    ctr = RepoCreate(name="a", type="container", url="u", upstream_name="x/y")
    assert service.build_repository_body(rpm, "/r/")["autopublish"] is True
    assert "autopublish" not in service.build_repository_body(ctr, "/r/")


def test_build_distribution_body_base_path_defaults_to_name():
    req = RepoCreate(name="a", type="rpm", url="u")
    assert service.build_distribution_body(req, "/r/")["base_path"] == "a"
    req2 = RepoCreate(name="a", type="rpm", url="u", base_path="deep/path")
    assert service.build_distribution_body(req2, "/r/")["base_path"] == "deep/path"


def test_join_repos_joins_by_href_and_parses_version():
    repositories = [{
        "pulp_href": "/repo/1/", "name": "r", "remote": "/rem/1/",
        "latest_version_href": "/repo/1/versions/7/",
        "pulp_last_updated": "2026-01-01T00:00:00Z",
    }]
    remotes = [{"pulp_href": "/rem/1/", "name": "r", "url": "http://u/", "policy": "on_demand"}]
    distributions = [{"repository": "/repo/1/", "base_path": "r",
                      "base_url": "http://m/pulp/content/r/"}]
    [repo] = service.join_repos("rpm", repositories, remotes, distributions)
    assert repo.latest_version == 7
    assert repo.url == "http://u/"
    assert repo.base_url == "http://m/pulp/content/r/"


def test_join_repos_tolerates_missing_remote_and_distribution():
    repositories = [{"pulp_href": "/repo/1/", "name": "r", "remote": None,
                     "latest_version_href": None}]
    [repo] = service.join_repos("deb", repositories, [], [])
    assert repo.url is None and repo.base_path is None and repo.latest_version is None


def test_map_task_progress_and_error():
    task = {
        "pulp_href": "/pulp/api/v3/tasks/abc-def/",
        "name": "pulp_rpm.app.tasks.synchronizing.synchronize",
        "state": "failed",
        "error": {"description": "boom"},
        "progress_reports": [
            {"message": "Downloading", "done": 3, "total": 10},
            {"message": "Parsing", "done": 5},
        ],
    }
    out = service.map_task(task)
    assert out.id == "abc-def"
    assert out.error == "boom"
    assert out.progress == ["Downloading: 3/10", "Parsing: 5"]


def _repo(**kw) -> Repo:
    base = {"name": "r", "type": "rpm", "base_path": "r"}
    return Repo(**{**base, **kw})


def test_client_config_rpm():
    text = service.client_config(_repo(), "https://mirror.lab.local")
    assert "baseurl=https://mirror.lab.local/pulp/content/r/" in text
    assert "[lab-r]" in text


def test_client_config_deb_uses_remote_suite():
    text = service.client_config(
        _repo(type="deb", deb_distributions="noble jammy", deb_components="main universe"),
        "https://mirror.lab.local",
    )
    assert "deb [trusted=yes] https://mirror.lab.local/pulp/content/r/ noble main universe" in text


def test_client_config_container_strips_scheme():
    text = service.client_config(_repo(type="container", base_path="tiny/hello"),
                                 "https://mirror.lab.local")
    assert "docker pull mirror.lab.local/tiny/hello:TAG" in text
