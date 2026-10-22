import csv
import io
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from lab_site import LAB_GRAPH
from site_fixture import ROOT, website
from sqlalchemy.orm import Session
from test_crawler_engine import create, finished

from app.main import create_app
from app.models import CrawlSession, Page


def test_dashboard_empty_and_counts_ignore_session_counters(client):
    empty = client.get("/api/dashboard").json()
    assert empty["sessions"] == empty["links"] == empty["fetched_pages"] == 0
    assert empty["recent"] == []
    ids = [create(client) for _ in range(6)]
    with Session(client.app.state.engine) as db:
        db.get(CrawlSession, ids[-1]).fetched_count = 999
        db.add(
            Page(
                session_id=ids[-1],
                normalized_url=ROOT,
                original_url=ROOT,
                depth=0,
                discovery_order=0,
                final_url=ROOT,
                error="parser error",
            )
        )
        db.commit()
    data = client.get("/api/dashboard").json()
    assert data["sessions"] == data["statuses"]["queued"] == 6
    assert data["discovered_pages"] == data["fetched_pages"] == data["errored_pages"] == 1
    assert [r["id"] for r in data["recent"]] == ids[::-1][:5]
    client.delete("/api/sessions/" + ids[-1])
    assert client.get("/api/dashboard").json()["fetched_pages"] == 0


def test_report_empty_escaping_validation_and_comparison_conflicts(client):
    session_id = create(client)
    url = f"/api/sessions/{session_id}/report"
    response = client.get(url)
    assert response.status_code == 200
    assert "Wyniki częściowe" in response.text and "czas (s): brak" in response.text
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    with Session(client.app.state.engine) as db:
        db.get(CrawlSession, session_id).error = '<img src=x onerror="alert(1)">'
        db.commit()
    report = client.get(url).text
    assert "&lt;img" in report and not BeautifulSoup(report, "html.parser").find("img")
    assert client.get("/api/sessions/nope/report").status_code == 422
    assert client.get(f"/api/sessions/{uuid4()}/report").status_code == 404
    assert (
        client.post("/api/reports/compare", json={"session_ids": [session_id]}).status_code == 422
    )
    other = create(client)
    assert (
        client.post("/api/reports/compare", json={"session_ids": [session_id, other]}).status_code
        == 409
    )


def test_all_eight_lab_requirements_real_tcp_report_csv_comparison_and_restart(database):
    settings, _ = database
    ids = []
    # I.1/2/3 and II.5/7: independently persisted parameter variants, real HTTP.
    variants = [
        {},
        {"strategy": "dfs"},
        {"link_types": "images_and_hyperlinks"},
        {"link_types": "all_links"},
        {"max_depth": 2, "scope": "web", "follow_external_urls": True},
    ]
    with (
        website(LAB_GRAPH) as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        for variant in variants:
            response = client.post(
                "/api/sessions",
                json={"start_url": ROOT + "/lab/", "config": {"request_delay_ms": 100, **variant}},
            )
            assert response.status_code == 201
            session_id = response.json()["id"]
            ids.append(session_id)
            assert client.post(f"/api/sessions/{session_id}/start").status_code == 200
            assert finished(client, session_id)["status"] == "completed"
        stats = client.get(f"/api/sessions/{ids[0]}/stats").json()
        assert stats["summary"]["fetched_pages"] == 22  # root + 21 subpages
        assert stats["summary"]["reached_depth"] == 3
        assert stats["summary"]["link_count"] == 39
        assert stats["summary"]["root_links"] == 6
        assert stats["summary"]["subpage_links"] == 33
        assert stats["summary"]["errored_pages"] == 1
        assert [d["fetched_pages"] for d in stats["per_depth"]] == [1, 3, 6, 12]
        graph = client.get(f"/api/sessions/{ids[0]}/graph").json()
        assert len(graph["edges"]) == sum(p["out_degree"] for p in stats["per_page"]) == 39
        comp = client.post("/api/compare", json={"session_ids": ids[:4]}).json()
        assert [r["link_count"] for r in comp["runs"]] == [39, 39, 40, 42]
        assert not comp["pairs"][0]["retrieval_order_equal"]
        assert comp["pairs"][0]["fetched"]["common"]["total"] == 22
        assert comp["pairs"][0]["fetched"]["left_only"]["total"] == 0
        assert comp["pairs"][0]["metadata_changes"]["total"] == 0
        # II.5: depth 2, follow external, not one-page, URL/Keyword CSV.
        b = client.get(f"/api/sessions/{ids[4]}").json()
        assert b["config"]["max_depth"] == 2 and b["config"]["follow_external_urls"]
        assert not b["config"]["process_one_page"] and b["fetched_count"] == 11
        exported = client.get(
            f"/api/sessions/{ids[4]}/export?fields=url,keywords&separator=semicolon"
        )
        rows = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig")), delimiter=";"))
        assert rows[0] == ["URL", "Keyword"] and len(rows) == 25
        assert rows[1][1] == "laboratorium, żółć"
        full_csv = client.get(f"/api/sessions/{ids[0]}/export").content.decode("utf-8-sig")
        assert "'=1+1" in full_csv
        # I.4/II.6/II.8: reports contain measurements, coverage, tradeoffs and real differences.
        report = client.get(f"/api/sessions/{ids[0]}/report")
        assert report.status_code == 200
        soup = BeautifulSoup(report.text, "html.parser")
        keyword = next(
            tr for tr in soup.select("tr") if [td.text for td in tr.select("td")][:1] == ["Keyword"]
        )
        assert [td.text for td in keyword.select("td")] == ["Keyword", "16", "6"]
        comparison = client.post("/api/reports/compare", json={"session_ids": [ids[4], ids[3]]})
        assert comparison.status_code == 200
        assert all(
            label in comparison.text
            for label in ("I.4", "II.6", "II.8", "SHA-256", "Wyniki częściowe")
        )
        measured = client.post("/api/compare", json={"session_ids": [ids[4], ids[3]]}).json()
        assert measured["pairs"][0]["fetched"]["left_only"]["total"] == 1
        assert measured["pairs"][0]["fetched"]["right_only"]["total"] == 12
        assert client.get("/api/dashboard").json()["fetched_pages"] == 99
        snapshot = client.get(f"/api/sessions/{ids[0]}").json()
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/sessions/{ids[0]}").json() == snapshot
        assert client.get(f"/api/sessions/{ids[0]}/report").status_code == 200


def test_comparison_report_preserves_budget_errors(client, monkeypatch):
    from app import comparison

    ids = [create(client), create(client)]
    for session_id in ids:
        client.post(f"/api/sessions/{session_id}/cancel")
    monkeypatch.setattr(comparison, "MAX_COMPARE_PAGES", -1)
    response = client.post("/api/reports/compare", json={"session_ids": ids})
    assert response.status_code == 413
    assert response.json()["code"] == "comparison_too_large"


def test_session_report_rejects_large_graph_without_truncation(client, monkeypatch):
    from app import reporting

    session_id = create(client)
    with Session(client.app.state.engine) as db:
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
    monkeypatch.setattr(reporting, "MAX_GRAPH_NODES", 0)
    response = client.get(f"/api/sessions/{session_id}/report")
    assert response.status_code == 413
    assert response.json()["code"] == "graph_too_large"


def test_comparison_report_escapes_downloaded_metadata_and_retains_hashes(client):
    from test_comparison import seeded_pair

    ids = seeded_pair(client)
    with Session(client.app.state.engine) as db:
        from sqlalchemy import select

        page = db.scalar(select(Page).where(Page.session_id == ids[0], Page.depth == 2))
        page.body = "<script>alert('x')</script>"
        db.commit()
    report = client.post("/api/reports/compare", json={"session_ids": ids})
    assert report.status_code == 200
    assert "&lt;script&gt;" in report.text and "sha256" in report.text
    assert not BeautifulSoup(report.text, "html.parser").find("script")


@pytest.mark.parametrize("status", ["queued", "running", "cancelled", "failed", "completed"])
def test_report_all_statuses_are_labeled(client, status):
    session_id = create(client)
    with Session(client.app.state.engine) as db:
        from app.models import SessionStatus

        db.get(CrawlSession, session_id).status = SessionStatus(status)
        db.commit()
    assert f"Status: {status}" in client.get(f"/api/sessions/{session_id}/report").text
