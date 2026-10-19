import asyncio
import json
import threading
import time

import httpx
import pytest
from alembic import command
from fastapi.testclient import TestClient
from site_fixture import ROOT, website
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crawler import engine as crawler_engine
from app.crawler.discovery import discover
from app.crawler.ownership import WorkerOwnership
from app.crawler.urls import CrawlError
from app.main import create_app
from app.models import CrawlEvent, CrawlSession, Link, LinkKind, LinkSelection, Page, SessionStatus


def create(client, **config):
    response = client.post(
        "/api/sessions",
        json={
            "start_url": ROOT,
            "config": {"request_delay_ms": 100, **config},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def finished(client, session_id, timeout=15):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        data = client.get(f"/api/sessions/{session_id}").json()
        if data["status"] != "running":
            return data
        time.sleep(0.01)
    pytest.fail("Crawler did not finish")


def rows(client, session_id):
    with Session(client.app.state.engine) as db:
        return db.scalars(
            select(Page).where(Page.session_id == session_id).order_by(Page.fetch_order)
        ).all()


@pytest.mark.parametrize(
    "strategy,paths",
    [
        ("bfs", ["/", "/a", "/b", "/a1", "/a2", "/b1", "/a11"]),
        ("dfs", ["/", "/a", "/a1", "/a11", "/a2", "/b", "/b1"]),
    ],
)
def test_real_tcp_bfs_dfs_cycles_dedup_persistence_events(database, strategy, paths):
    settings, _ = database
    with (
        website() as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        session_id = create(client, strategy=strategy)
        assert client.post(f"/api/sessions/{session_id}/start").status_code == 200
        result = finished(client, session_id)
        assert result["status"] == "completed", result
        assert result["stop_reason"] == "frontier_exhausted"
        assert result["fetched_count"] == 7 and result["discovered_count"] == 7
        assert result["link_count"] == 8 and result["error_count"] == 0
        assert [
            page.normalized_url.removeprefix(ROOT) for page in rows(client, session_id)
        ] == paths
        assert [path for path, _, _ in site.requests if path != "/robots.txt"] == paths
        assert sum(path == "/robots.txt" for path, _, _ in site.requests) == 1
        assert all(
            page.title is None and page.body is not None for page in rows(client, session_id)
        )
        with Session(client.app.state.engine) as db:
            events = db.scalars(
                select(CrawlEvent)
                .where(CrawlEvent.session_id == session_id)
                .order_by(CrawlEvent.id)
            ).all()
            assert events[-1].kind == "completed"
            assert events[-1].data["fetched_count"] == 7
            cursor = events[-2].id
            assert (
                db.scalar(
                    select(func.count()).select_from(Link).where(Link.session_id == session_id)
                )
                == 8
            )
        stream = client.get(
            f"/api/sessions/{session_id}/events", headers={"Last-Event-ID": str(cursor)}
        )
        assert stream.status_code == 200
        assert "event: completed\n" in stream.text and "event: page_fetched\n" not in stream.text
        event_data = next(
            line[6:] for line in stream.text.splitlines() if line.startswith("data: ")
        )
        assert json.loads(event_data)["fetched_count"] == 7
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/sessions/{session_id}").json() == result


@pytest.mark.parametrize(
    "config,count,reason",
    [
        ({"max_depth": 0}, 1, "frontier_exhausted"),
        ({"max_depth": 1}, 3, "frontier_exhausted"),
        ({"process_one_page": True}, 1, "frontier_exhausted"),
        ({"max_pages": 2}, 2, "page_limit"),
    ],
)
def test_depth_page_one_page_limits(database, config, count, reason):
    settings, _ = database
    with (
        website() as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        session_id = create(client, **config)
        client.post(f"/api/sessions/{session_id}/start")
        result = finished(client, session_id)
        assert result["fetched_count"] == count, result
        assert result["stop_reason"] == reason
        assert len([path for path, _, _ in site.requests if path != "/robots.txt"]) == count
        assert result["discovered_count"] >= count


@pytest.mark.parametrize(
    "scope,external,expected",
    [
        ("server", False, 1),
        ("server", True, 1),
        ("web", False, 1),
        ("web", True, 2),
    ],
)
def test_scope_external_recorded_independently_from_following(database, scope, external, expected):
    settings, _ = database
    pages = {"/": '<a href="http://other.example/out">External</a>', "/out": "outside"}
    with (
        website(pages) as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        session_id = create(client, scope=scope, follow_external_urls=external)
        client.post(f"/api/sessions/{session_id}/start")
        result = finished(client, session_id)
        assert result["fetched_count"] == expected
        assert result["discovered_count"] == 2
        with Session(client.app.state.engine) as db:
            link = db.scalar(select(Link).where(Link.session_id == session_id))
            assert link.is_external
            assert link.is_followed == (expected == 2)


@pytest.mark.parametrize(
    "mode,kinds",
    [
        ("hyperlinks", {LinkKind.HYPERLINK}),
        ("images_and_hyperlinks", {LinkKind.HYPERLINK, LinkKind.IMAGE}),
        ("all_links", {LinkKind.HYPERLINK, LinkKind.IMAGE, LinkKind.STYLESHEET, LinkKind.SCRIPT}),
    ],
)
def test_link_selection_assets_not_crawled_as_html(database, mode, kinds):
    settings, _ = database
    with (
        website() as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        session_id = create(client, link_types=mode, process_one_page=True)
        client.post(f"/api/sessions/{session_id}/start")
        result = finished(client, session_id)
        assert result["fetched_count"] == 1 and result["discovered_count"] == 3
        with Session(client.app.state.engine) as db:
            links = db.scalars(select(Link).where(Link.session_id == session_id)).all()
            assert {link.kind for link in links} == kinds
        assert all(
            path not in {"/image.png", "/style.css", "/app.js"} for path, _, _ in site.requests
        )


def test_bad_page_does_not_lose_successes_and_redirect_final_url(database):
    settings, _ = database
    pages = {
        "/": '<a href="/bad">Bad</a><a href="/redirect">Good</a>',
        "/bad": (503, {}, "error"),
        "/redirect": (302, {"Location": "/good"}, ""),
        "/good": "good",
    }
    with (
        website(pages) as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        session_id = create(client)
        client.post(f"/api/sessions/{session_id}/start")
        result = finished(client, session_id)
        assert result["status"] == "completed" and result["fetched_count"] == 2
        assert result["error_count"] == 1
        saved = {page.normalized_url: page for page in rows(client, session_id)}
        assert saved[ROOT + "/bad"].http_status == 503
        assert saved[ROOT + "/redirect"].final_url == ROOT + "/good"


def test_dfs_reexpands_shorter_path_without_refetch(database):
    settings, _ = database
    pages = {
        "/": '<a href="/a">A</a><a href="/b">B</a>',
        "/a": '<a href="/x">X</a>',
        "/x": '<a href="/z">Z</a>',
        "/z": '<a href="/end">End</a>',
        "/b": '<a href="/z">short path</a>',
        "/end": "end",
    }
    with (
        website(pages) as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        session_id = create(client, strategy="dfs", max_depth=3)
        client.post(f"/api/sessions/{session_id}/start")
        result = finished(client, session_id)
        assert result["fetched_count"] == 6, result
        assert sum(path == "/z" for path, _, _ in site.requests) == 1
        depths = {page.normalized_url: page.depth for page in rows(client, session_id)}
        assert depths[ROOT + "/z"] == 2 and depths[ROOT + "/end"] == 3


def test_cancel_aborts_active_request_no_later_requests_and_idempotency(database):
    settings, _ = database
    with website(
        {"/": '<a href="/slow">Slow</a><a href="/later">Later</a>', "/slow": "slow"}
    ) as site:
        with TestClient(create_app(settings, transport_factory=site.transport)) as client:
            session_id = create(client)
            url = f"/api/sessions/{session_id}"
            assert client.post(url + "/start").json()["status"] == "running"
            assert client.post(url + "/start").status_code == 200
            assert site.entered.wait(5)
            assert client.patch(url, json={"start_url": "https://example.com"}).status_code == 409
            assert client.delete(url).status_code == 409
            before = time.monotonic()
            result = client.post(url + "/cancel").json()
            assert time.monotonic() - before < 1
            assert result["status"] == "cancelled" and result["fetched_count"] == 1
            assert client.post(url + "/cancel").json() == result
            assert client.post(url + "/start").status_code == 409
            site.release.set()
            time.sleep(0.1)
            assert not any(path == "/later" for path, _, _ in site.requests)
            assert "event: cancelled" in client.get(url + "/events").text


def test_time_limit_and_request_timeout_persist_partial_data(database):
    settings, _ = database
    with website({"/": '<a href="/slow">Slow</a>', "/slow": "slow"}) as site:
        with TestClient(create_app(settings, transport_factory=site.transport)) as client:
            session_id = create(client, max_duration_seconds=1)
            client.post(f"/api/sessions/{session_id}/start")
            result = finished(client, session_id)
            assert result["stop_reason"] == "time_limit" and result["fetched_count"] == 1


def test_robots_denied_page_preserves_other_results(database):
    settings, _ = database
    with website(robots="User-agent: *\nDisallow: /a") as site:
        with TestClient(create_app(settings, transport_factory=site.transport)) as client:
            session_id = create(client)
            client.post(f"/api/sessions/{session_id}/start")
            result = finished(client, session_id)
            assert result["fetched_count"] == 3 and result["error_count"] == 1
            assert not any(path == "/a" for path, _, _ in site.requests)
            assert sum(path == "/robots.txt" for path, _, _ in site.requests) == 1


def test_cancel_queued_unknown_ids_and_cursor_validation(client):
    session_id = create(client)
    url = f"/api/sessions/{session_id}"
    assert client.post(url + "/cancel").json()["status"] == "cancelled"
    assert client.post(url + "/cancel").status_code == 200
    assert client.post(url + "/start").status_code == 409
    assert client.get(url + "/events?after=-1").status_code == 422
    assert client.get(url + "/events", headers={"Last-Event-ID": "bad"}).status_code == 422


def test_stale_running_recovery_preserves_pages_and_exclusive_worker(database):
    settings, _ = database
    with TestClient(create_app(settings)) as client:
        session_id = create(client)
        with Session(client.app.state.engine) as db:
            crawl = db.get(CrawlSession, session_id)
            crawl.status = SessionStatus.RUNNING
            db.add(
                Page(
                    session_id=session_id,
                    normalized_url=ROOT,
                    original_url=ROOT,
                    depth=0,
                    discovery_order=0,
                )
            )
            db.commit()
        other_owner = WorkerOwnership(settings.database_url)
        with pytest.raises(RuntimeError, match="one API worker"):
            other_owner.acquire()
    with TestClient(create_app(settings)) as client:
        result = client.get(f"/api/sessions/{session_id}").json()
        assert result["status"] == "failed" and result["stop_reason"] == "interrupted"
        assert len(rows(client, session_id)) == 1
        assert "event: failure" in client.get(f"/api/sessions/{session_id}/events").text


def test_migration_preserves_populated_phase_two_data_on_upgrade_and_downgrade(database):
    settings, migration = database
    with TestClient(create_app(settings)) as client:
        session_id = create(client)
        with Session(client.app.state.engine) as db:
            page = Page(
                session_id=session_id,
                normalized_url=ROOT,
                original_url=ROOT,
                depth=0,
                discovery_order=0,
            )
            db.add(page)
            db.flush()
            db.add(
                Link(
                    session_id=session_id,
                    source_page_id=page.id,
                    target_url=ROOT,
                    kind=LinkKind.HYPERLINK,
                )
            )
            db.commit()
    command.downgrade(migration, "0002_sessions")
    command.upgrade(migration, "head")
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/sessions/{session_id}").status_code == 200
        assert len(rows(client, session_id)) == 1
        with Session(client.app.state.engine) as db:
            assert db.scalar(select(func.count()).select_from(Link)) == 1


def test_discovery_base_relative_links_and_no_javascript_execution():
    refs = discover(
        b'<base href="/nested/"><a href="a#x">a</a><img src="../x.png">'
        b'<script src="/x.js">throw 1</script><a href="javascript:alert(1)">bad</a>',
        ROOT + "/",
        LinkSelection.ALL_LINKS,
    )
    assert [reference.url for reference in refs] == [
        ROOT + "/nested/a",
        ROOT + "/x.png",
        ROOT + "/x.js",
    ]


def test_capacity_limit_and_graceful_shutdown(database):
    settings, _ = database

    async def blocked(request):
        await asyncio.sleep(60)
        return httpx.Response(200, text="unused")

    with TestClient(
        create_app(settings, transport_factory=lambda: httpx.MockTransport(blocked))
    ) as client:
        ids = [create(client, respect_robots=False) for _ in range(5)]
        for session_id in ids[:4]:
            assert client.post(f"/api/sessions/{session_id}/start").status_code == 200
        rejected = client.post(f"/api/sessions/{ids[4]}/start")
        assert rejected.status_code == 429
        assert client.get(f"/api/sessions/{ids[4]}").json()["status"] == "queued"
    with TestClient(create_app(settings)) as client:
        for session_id in ids[:4]:
            result = client.get(f"/api/sessions/{session_id}").json()
            assert result["status"] == "cancelled"
            assert result["stop_reason"] == "server_shutdown"


@pytest.mark.parametrize("cap", ["MAX_DISCOVERED_PAGES", "MAX_SESSION_LINKS"])
def test_discovery_budgets_stop_without_losing_fetched_page(database, monkeypatch, cap):
    settings, _ = database
    monkeypatch.setattr(crawler_engine, cap, 1)
    with (
        website() as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        session_id = create(client)
        client.post(f"/api/sessions/{session_id}/start")
        result = finished(client, session_id)
        assert result["fetched_count"] == 1
        assert result["error_count"] == 1
        assert result["stop_reason"] in {"link_limit", "discovery_limit"}
        assert [path for path, _, _ in site.requests] == ["/robots.txt", "/"]
        assert len(rows(client, session_id)) == 1
        assert rows(client, session_id)[0].body == "AA againB"


def test_factory_failure_does_not_leave_running_session(database):
    settings, _ = database

    def broken():
        raise RuntimeError("fixture factory error")

    with TestClient(create_app(settings, transport_factory=broken)) as client:
        session_id = create(client)
        assert client.post(f"/api/sessions/{session_id}/start").status_code == 503
        result = client.get(f"/api/sessions/{session_id}").json()
        assert result["status"] == "failed" and result["stop_reason"] == "internal_error"


def test_unfinished_html_token_is_bounded():
    with pytest.raises(CrawlError) as error:
        discover(b'<a href="' + b"x" * 70000, ROOT + "/", LinkSelection.HYPERLINKS)
    assert error.value.code == "parse_limit"


def test_html_discovery_cooperatively_stops_on_cancellation():
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(CrawlError) as error:
        discover(b'<a href="/a">a</a>', ROOT + "/", LinkSelection.HYPERLINKS, cancelled=cancelled)
    assert error.value.code == "parse_timeout"
