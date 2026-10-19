from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import CrawlSession, SessionStatus


def create(client, **changes):
    response = client.post("/api/sessions", json={"start_url": "https://example.com", **changes})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_read_list_update_delete(client):
    assert client.get("/api/sessions").json() == {"items": [], "total": 0, "offset": 0, "limit": 20}
    response = client.post("/api/sessions", json={"start_url": "HTTPS://EXAMPLE.COM/path#fragment"})
    assert response.status_code == 201
    item = response.json()
    assert response.headers["location"] == f"/api/sessions/{item['id']}"
    assert item["start_url"] == "https://example.com/path"
    assert item["status"] == "queued"
    assert datetime.fromisoformat(item["created_at"]).utcoffset().total_seconds() == 0
    assert item["started_at"] is None and item["finished_at"] is None
    assert item["error"] is None
    assert (item["discovered_count"], item["fetched_count"], item["error_count"]) == (0, 0, 0)
    assert item["config"]["respect_robots"] is True
    assert item["config"]["max_depth"] == 3
    url = response.headers["location"]
    assert client.get(url).json() == item
    assert client.get("/api/sessions").json()["items"] == [item]
    updated = client.patch(
        url,
        json={
            "start_url": "https://example.org",
            "config": {
                "strategy": "dfs",
                "scope": "web",
                "link_types": "all_links",
                "max_depth": 0,
                "max_pages": 1,
                "timeout_seconds": 2.5,
                "request_delay_ms": 100,
                "max_duration_seconds": 60,
                "max_response_bytes": 1024,
                "max_redirects": 0,
                "concurrency": 1,
                "respect_robots": False,
                "follow_external_urls": True,
                "process_one_page": True,
            },
        },
    )
    assert updated.status_code == 200
    saved = updated.json()
    assert saved["id"] == item["id"] and saved["created_at"] == item["created_at"]
    assert saved["config"]["strategy"] == "dfs"
    assert saved["config"]["timeout_seconds"] == 2.5
    assert saved["config"]["follow_external_urls"] is True
    assert client.get(url).json() == saved
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.delete(url).status_code == 404
    assert client.get("/api/sessions").json()["total"] == 0


def test_partial_update_preserves_unmentioned_part_and_config_replacement(client):
    item = create(client, config={"strategy": "dfs"})
    url = f"/api/sessions/{item['id']}"
    changed = client.patch(url, json={"start_url": "https://example.org/"}).json()
    assert changed["config"] == item["config"]
    changed = client.patch(url, json={"config": {"max_depth": 1}}).json()
    assert changed["start_url"] == "https://example.org/"
    assert changed["config"]["strategy"] == "bfs"  # config is a full replacement with defaults
    assert changed["config"]["max_depth"] == 1


def test_pagination_and_status_filter(client):
    items = [create(client) for _ in range(4)]
    with Session(client.app.state.engine) as db:
        db.get(CrawlSession, items[0]["id"]).status = SessionStatus.COMPLETED
        db.commit()
    page = client.get("/api/sessions?limit=2&offset=1").json()
    assert page["total"] == 4 and page["limit"] == 2 and page["offset"] == 1
    assert [row["id"] for row in page["items"]] == [items[2]["id"], items[1]["id"]]
    assert client.get("/api/sessions?offset=100").json()["items"] == []
    filtered = client.get("/api/sessions?status=completed").json()
    assert filtered["total"] == 1 and filtered["items"][0]["id"] == items[0]["id"]


def test_persistence_across_app_restart(database):
    settings, _ = database
    with TestClient(create_app(settings)) as first:
        item = create(first, config={"strategy": "dfs", "max_depth": 2})
    with TestClient(create_app(settings)) as second:
        assert second.get(f"/api/sessions/{item['id']}").json() == item
        assert second.get("/api/sessions").json()["total"] == 1


@pytest.mark.parametrize("status", list(SessionStatus))
def test_status_is_persisted_edit_and_delete_guards(client, status):
    item = create(client)
    with Session(client.app.state.engine) as db:
        db.get(CrawlSession, item["id"]).status = status
        db.commit()
    url = f"/api/sessions/{item['id']}"
    assert client.get(url).json()["status"] == status.value
    assert client.patch(url, json={"config": {"max_depth": 1}}).status_code == (
        200 if status == SessionStatus.QUEUED else 409
    )
    response = client.delete(url)
    assert response.status_code == (409 if status == SessionStatus.RUNNING else 204)
    if status == SessionStatus.RUNNING:
        assert response.json()["code"] == "session_running"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"start_url": None},
        {"config": None},
        {"status": "completed"},
        {"config": {"max_pages": 0}},
    ],
)
def test_invalid_patch_is_atomic(client, payload):
    item = create(client)
    url = f"/api/sessions/{item['id']}"
    assert client.patch(url, json=payload).status_code == 422
    assert client.get(url).json() == item


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com",
        "javascript:alert(1)",
        "",
        "not-a-url",
        "https://user:secret@example.com",
        "https://@example.com",
        "http://localhost/",
        "http://127.0.0.1",
        "http://224.0.0.1",
        "http://[ff02::1]",
        "http://[fec0::1]",
        "http://[2606:4700:4700::1111%25eth0]",
        "http://10.0.0.1",
        "http://169.254.169.254",
        "http://[::1]",
        "http://[::ffff:127.0.0.1]",
        "http://2130706433",
        "http://0x7f000001",
        "http://service.internal",
        "http://x.localhost",
        "https://bad_host.example",
        "https://example.com:8080",
        " https://example.com",
        "https://example.com/with space",
        "https://example.com/\nheader",
        "https://example.com/\\path",
        "https://-bad.example",
    ],
)
def test_invalid_start_url(client, url):
    response = client.post("/api/sessions", json={"start_url": url})
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"
    assert "secret" not in response.text
    assert client.get("/api/sessions").json()["total"] == 0


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://example.com", "https://example.com/"),
        ("https://żółw.pl", "https://xn--w-uga1v8h.pl/"),
        ("https://8.8.8.8", "https://8.8.8.8/"),
        ("https://[2606:4700:4700::1111]", "https://[2606:4700:4700::1111]/"),
    ],
)
def test_valid_start_urls(client, url, expected):
    assert create(client, start_url=url)["start_url"] == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("strategy", "random"),
        ("scope", "directory"),
        ("link_types", "scripts"),
        ("max_depth", -1),
        ("max_depth", 21),
        ("max_depth", True),
        ("max_pages", 0),
        ("max_pages", 10001),
        ("max_pages", "10"),
        ("max_pages", 1.5),
        ("timeout_seconds", 0),
        ("timeout_seconds", 61),
        ("timeout_seconds", True),
        ("request_delay_ms", 0),
        ("request_delay_ms", 60001),
        ("max_duration_seconds", 3601),
        ("max_response_bytes", 1023),
        ("max_response_bytes", 10485761),
        ("max_redirects", -1),
        ("max_redirects", 11),
        ("concurrency", 0),
        ("concurrency", 9),
        ("respect_robots", "true"),
        ("follow_external_urls", 1),
        ("process_one_page", None),
        ("unknown", 123),
    ],
)
def test_config_validation(client, field, value):
    response = client.post(
        "/api/sessions", json={"start_url": "https://example.com", "config": {field: value}}
    )
    assert response.status_code == 422, response.text
    assert response.json()["details"]
    assert client.get("/api/sessions").json()["total"] == 0


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=101", "offset=-1", "offset=9223372036854775808", "status=bogus"]
)
def test_invalid_pagination(client, query):
    assert client.get(f"/api/sessions?{query}").status_code == 422


def test_missing_and_malformed_ids(client):
    url = f"/api/sessions/{uuid4()}"
    for response in [
        client.get(url),
        client.patch(url, json={"start_url": "https://example.com"}),
        client.delete(url),
    ]:
        assert response.status_code == 404
        assert response.json() == {
            "code": "session_not_found",
            "message": "Nie znaleziono sesji",
            "details": [],
        }
    assert client.get("/api/sessions/not-a-uuid").status_code == 422
    assert (
        client.post(
            "/api/sessions", content="{", headers={"Content-Type": "application/json"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/sessions", json={"start_url": "https://example.com", "status": "running"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_mutation_cors(client, method):
    response = client.options(
        "/api/sessions",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_maximum_config_boundaries(client):
    config = {
        "max_depth": 20,
        "max_pages": 10000,
        "timeout_seconds": 60,
        "request_delay_ms": 60000,
        "max_duration_seconds": 3600,
        "max_response_bytes": 10485760,
        "max_redirects": 10,
        "concurrency": 8,
    }
    saved = create(client, config=config)
    assert all(saved["config"][field] == value for field, value in config.items())


def test_unmigrated_database_returns_safe_503(tmp_path):
    from app.core.config import Settings

    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{(tmp_path / 'empty.db').as_posix()}"
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/sessions")
        assert response.status_code == 503
        assert response.json() == {
            "code": "database_unavailable",
            "message": "Baza danych jest niedostępna",
            "details": [],
        }
        assert client.get("/health").status_code == 200  # Health only checks connectivity.
