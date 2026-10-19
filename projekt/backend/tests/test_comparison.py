import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from site_fixture import ROOT, website
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_crawler_engine import create, finished

from app import comparison
from app.main import create_app
from app.models import CrawlSession, Link, LinkKind, Page, SessionStatus


def experiment(client, variants=None):
    response = client.post(
        "/api/experiments",
        json={
            "name": "BFS / DFS",
            "start_url": ROOT,
            "variants": variants
            or [
                {"strategy": "bfs", "request_delay_ms": 100},
                {"strategy": "dfs", "request_delay_ms": 100},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def compare(client, ids, **params):
    response = client.post("/api/compare", json={"session_ids": ids}, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_experiment_real_bfs_dfs_equal_graph_different_order_restart(database):
    settings, _ = database
    with (
        website() as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        saved = experiment(client)
        assert saved["state"] == "queued" and len(saved["sessions"]) == 2
        assert all(value["configuration_locked"] for value in saved["sessions"])
        ids = [value["id"] for value in saved["sessions"]]
        assert saved["sessions"][0]["config"]["strategy"] == "bfs"
        assert saved["sessions"][1]["config"]["strategy"] == "dfs"
        assert (
            client.patch(
                f"/api/sessions/{ids[0]}", json={"start_url": "https://example.org"}
            ).status_code
            == 409
        )
        path = f"/api/experiments/{saved['id']}"
        launch = client.post(path + "/start").json()
        assert launch["errors"] == []
        assert client.post(path + "/start").json()["errors"] == []
        for session_id in ids:
            assert finished(client, session_id)["status"] == "completed"
        result = compare(client, ids)
        pair = result["pairs"][0]
        assert pair["config_changes"] == {"strategy": ["bfs", "dfs"]}
        assert pair["fetched"]["common"]["total"] == 7
        assert pair["fetched"]["left_only"]["total"] == pair["fetched"]["right_only"]["total"] == 0
        assert pair["edges"]["common"]["total"] == 7
        assert pair["edges"]["multiplicity_changes"]["total"] == 0
        assert pair["metadata_changes"]["total"] == pair["depth_changes"]["total"] == 0
        assert not pair["retrieval_order_equal"]
        assert all(
            run["elapsed_seconds"] > 0 and run["reached_depth"] == 3 for run in result["runs"]
        )
        assert len([path for path, _, _ in site.requests if path != "/robots.txt"]) == 14
        assert compare(client, ids) == result
        assert client.get(path).json()["state"] == "finished"
    with TestClient(create_app(settings)) as client:
        assert compare(client, ids) == result
        assert client.get(path).json()["sessions"][0]["config"]["strategy"] == "bfs"
        assert client.delete(path).status_code == 204
        assert all(
            client.get(f"/api/sessions/{session_id}").status_code == 200 for session_id in ids
        )


@pytest.mark.parametrize(
    "variants,expected",
    [
        ([{"strategy": "bfs", "max_pages": 3}, {"strategy": "dfs", "max_pages": 3}], "order"),
        ([{"max_depth": 0}, {"max_depth": 3}], "depth"),
        ([{"scope": "server"}, {"scope": "web", "follow_external_urls": True}], "scope"),
        (
            [
                {"link_types": "hyperlinks"},
                {"link_types": "images_and_hyperlinks"},
                {"link_types": "all_links"},
            ],
            "links",
        ),
    ],
)
def test_parameter_variants_have_measured_set_differences(database, variants, expected):
    settings, _ = database
    pages = {
        "/": '<a href="/a">A</a><a href="/b">B</a>'
        '<a href="http://other.example/out">out</a><img src="/x.png"><script src="/x.js"></script>',
        "/a": '<a href="/a1">deep</a>',
        "/b": "B",
        "/a1": "A1",
        "/out": "outside",
    }
    with (
        website(pages) as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        saved = experiment(client, [{"request_delay_ms": 100, **config} for config in variants])
        ids = [value["id"] for value in saved["sessions"]]
        client.post(f"/api/experiments/{saved['id']}/start")
        for session_id in ids:
            finished(client, session_id)
        result = compare(client, ids)
        pair = result["pairs"][0]
        if expected == "order":
            assert pair["fetched"]["left_only"]["items"] == [ROOT + "/b"]
            assert pair["fetched"]["right_only"]["items"] == [ROOT + "/a1"]
        if expected == "depth":
            assert [run["reached_depth"] for run in result["runs"]] == [0, 2]
            assert pair["fetched"]["right_only"]["total"] == 3
        if expected == "scope":
            assert pair["fetched"]["right_only"]["items"] == ["http://other.example/out"]
        if expected == "links":
            assert [run["link_count"] for run in result["runs"]] == [4, 5, 6]
            assert pair["edges"]["right_only"]["items"][0]["kind"] == "image"
            assert result["pairs"][1]["edges"]["right_only"]["total"] == 2


def seeded_pair(client):
    ids = [create(client), create(client)]
    start = datetime(2026, 10, 19, tzinfo=UTC)
    with Session(client.app.state.engine) as db:
        for index, session_id in enumerate(ids):
            crawl = db.get(CrawlSession, session_id)
            crawl.status = SessionStatus.COMPLETED
            crawl.stop_reason = "frontier_exhausted"
            crawl.started_at, crawl.finished_at = start, start + timedelta(seconds=index + 1)
            root = Page(
                session_id=session_id,
                normalized_url=ROOT + "/",
                original_url=ROOT,
                final_url=ROOT + "/",
                depth=0,
                fetch_order=0,
                discovery_order=0,
            )
            common = Page(
                session_id=session_id,
                normalized_url=ROOT + "/common",
                original_url="x",
                final_url=ROOT + "/common",
                depth=2 - index,
                fetch_order=1,
                discovery_order=1,
                title=None if index == 0 else "",
                description="A" if index == 0 else "B",
                keywords="żółć",
                body="x" * 600 + ("A" if index == 0 else "B"),
            )
            db.add_all([root, common])
            db.flush()
            for _ in range(2 - index):
                db.add(
                    Link(
                        session_id=session_id,
                        source_page_id=root.id,
                        target_url=common.normalized_url,
                        target_page_id=common.id,
                        kind=LinkKind.HYPERLINK,
                    )
                )
        db.commit()
    return ids


def test_full_metadata_hash_null_empty_duplicates_depth_and_measured_time(client):
    ids = seeded_pair(client)
    result = compare(client, ids, limit=1)
    assert [run["elapsed_seconds"] for run in result["runs"]] == [1, 2]
    pair = result["pairs"][0]
    change = pair["metadata_changes"]["items"][0]
    assert set(change["fields"]) == {"title", "description", "body"}
    assert change["fields"]["title"][0]["value"] is None
    assert change["fields"]["title"][1]["value"] == ""
    a, b = change["fields"]["body"]
    assert a["truncated"] and b["truncated"] and a["value"] == b["value"]
    assert a["length"] == b["length"] == 601 and a["sha256"] != b["sha256"]
    assert pair["depth_changes"]["items"] == [{"url": ROOT + "/common", "left": 2, "right": 1}]
    assert pair["edges"]["multiplicity_changes"]["items"][0]["left_count"] == 2
    assert pair["edges"]["multiplicity_changes"]["items"][0]["right_count"] == 1
    assert pair["fetched"]["common"]["total"] == 2 and len(pair["fetched"]["common"]["items"]) == 1
    second = compare(client, ids, limit=1, offset=1)
    assert second["pairs"][0]["fetched"]["common"]["items"] == [ROOT + "/common"]
    assert second["pairs"][0]["metadata_changes"]["total"] == 1
    assert second["pairs"][0]["metadata_changes"]["items"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "start_url": ROOT, "variants": [{}, {}]},
        {"name": "x", "start_url": ROOT, "variants": [{}]},
        {"name": "x", "start_url": ROOT, "variants": [{}] * 5},
        {"name": "x", "start_url": "http://127.0.0.1", "variants": [{}, {}]},
        {"name": "x", "start_url": ROOT, "variants": [{}, {"max_depth": True}]},
    ],
)
def test_invalid_experiment_is_atomic(client, payload):
    assert client.post("/api/experiments", json=payload).status_code == 422
    assert client.get("/api/experiments").json()["total"] == 0
    assert client.get("/api/sessions").json()["total"] == 0


def test_read_list_delete_members_incomplete_and_unlock(client):
    first, second = experiment(client), experiment(client)
    listing = client.get("/api/experiments?limit=1").json()
    assert listing["total"] == 2 and listing["items"][0]["id"] == second["id"]
    assert client.get("/api/experiments?offset=1&limit=1").json()["items"][0]["id"] == first["id"]
    path = f"/api/experiments/{first['id']}"
    one, two = [value["id"] for value in first["sessions"]]
    assert client.delete(f"/api/sessions/{one}").status_code == 204
    assert client.get(path).json()["state"] == "incomplete"
    assert client.post(path + "/start").status_code == 409
    assert client.delete(path).status_code == 204
    assert client.patch(f"/api/sessions/{two}", json={"config": {}}).status_code == 200
    assert client.get(path).status_code == 404 and client.delete(path).status_code == 404
    for route in [
        "/api/experiments/not-uuid",
        "/api/experiments?limit=0",
        "/api/experiments?offset=-1",
    ]:
        assert client.get(route).status_code == 422


def test_comparison_validation_readiness_limits_and_partial_notes(client, monkeypatch):
    ids = seeded_pair(client)
    for payload in [
        {"session_ids": [ids[0]]},
        {"session_ids": [ids[0], ids[0]]},
        {"session_ids": ["bad", ids[1]]},
        {"session_ids": ids, "extra": True},
    ]:
        assert client.post("/api/compare", json=payload).status_code == 422
    assert (
        client.post("/api/compare", json={"session_ids": [ids[0], str(uuid4())]}).status_code == 404
    )
    for query in ["offset=-1", "limit=0", "limit=101"]:
        assert client.post("/api/compare?" + query, json={"session_ids": ids}).status_code == 422
    with Session(client.app.state.engine) as db:
        run = db.get(CrawlSession, ids[1])
        run.start_url = "https://other.example/"
        db.commit()
    assert client.post("/api/compare", json={"session_ids": ids}).status_code == 409
    with Session(client.app.state.engine) as db:
        run = db.get(CrawlSession, ids[1])
        run.start_url = ROOT + "/"
        run.status = SessionStatus.RUNNING
        db.commit()
    assert client.post("/api/compare", json={"session_ids": ids}).status_code == 409
    with Session(client.app.state.engine) as db:
        run = db.get(CrawlSession, ids[1])
        run.status = SessionStatus.CANCELLED
        db.commit()
    assert any("częściowe" in note for note in compare(client, ids)["notes"])
    for setting in ["MAX_COMPARE_PAGES", "MAX_COMPARE_LINKS", "MAX_COMPARE_TEXT_BYTES"]:
        with monkeypatch.context() as context:
            context.setattr(comparison, setting, 0)
            assert client.post("/api/compare", json={"session_ids": ids}).status_code == 413
    monkeypatch.setattr(comparison, "MAX_COMPARE_SECONDS", -1)
    assert client.post("/api/compare", json={"session_ids": ids}).status_code == 503


def test_worker_capacity_partial_launch_retry_and_idempotence(database):
    settings, _ = database

    async def blocked(request):
        await asyncio.sleep(60)
        return httpx.Response(200, text="unused")

    with TestClient(
        create_app(settings, transport_factory=lambda: httpx.MockTransport(blocked))
    ) as client:
        existing = [create(client, respect_robots=False) for _ in range(3)]
        for session_id in existing:
            client.post(f"/api/sessions/{session_id}/start")
        saved = experiment(client, [{"respect_robots": False}] * 4)
        path = f"/api/experiments/{saved['id']}"
        launch = client.post(path + "/start").json()
        assert len(launch["errors"]) == 3 and all(
            error["status"] == 429 for error in launch["errors"]
        )
        assert sum(value["status"] == "running" for value in launch["experiment"]["sessions"]) == 1
        for session_id in existing:
            client.post(f"/api/sessions/{session_id}/cancel")
        assert client.post(path + "/start").json()["errors"] == []
        assert client.post(path + "/start").json()["errors"] == []
        with Session(client.app.state.engine) as db:
            assert db.scalar(select(func.count()).select_from(CrawlSession)) == 7
