from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from site_fixture import ROOT, website
from sqlalchemy.orm import Session
from test_crawler_engine import create, finished

from app import api
from app.main import create_app
from app.models import Link, LinkKind, Page


def assert_graph_invariants(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    edges, summary = graph["edges"], graph["summary"]
    assert len(nodes) == summary["node_count"]
    assert len(edges) == summary["link_count"]
    assert len({(edge["source"], edge["target"]) for edge in edges}) == summary["unique_relations"]
    assert sum(node["in_degree"] for node in nodes.values()) == len(edges)
    assert sum(node["out_degree"] for node in nodes.values()) == len(edges)
    for node_id, node in nodes.items():
        ins = [edge for edge in edges if edge["target"] == node_id]
        outs = [edge for edge in edges if edge["source"] == node_id]
        assert node["in_degree"] == len(ins) and node["out_degree"] == len(outs)
        assert node["unique_in_degree"] == len({edge["source"] for edge in ins})
        assert node["unique_out_degree"] == len({edge["target"] for edge in outs})
        assert all(edge["target_url"] == nodes[edge["target"]]["url"] for edge in outs)


@pytest.mark.parametrize("strategy", ["bfs", "dfs"])
def test_real_crawl_graph_stats_persisted_after_restart(database, strategy):
    settings, _ = database
    with (
        website() as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        session_id = create(client, strategy=strategy, link_types="all_links")
        path = f"/api/sessions/{session_id}"
        client.post(path + "/start")
        assert finished(client, session_id)["status"] == "completed"
        graph = client.get(path + "/graph").json()
        assert_graph_invariants(graph)
        assert graph["summary"] == {
            "node_count": 10,
            "page_count": 7,
            "resource_target_count": 3,
            "fetched_pages": 7,
            "errored_pages": 0,
            "reached_depth": 3,
            "discovered_depth": 3,
            "link_count": 11,
            "unique_relations": 10,
            "internal_links": 11,
            "external_links": 0,
            "root_links": 6,
            "root_unique_targets": 5,
            "subpage_links": 5,
            "subpage_unique_targets": 5,
        }
        stats = client.get(path + "/stats").json()
        assert stats["summary"] == graph["summary"]
        assert stats["per_depth"] == [
            {"depth": 0, "pages": 1, "fetched_pages": 1, "outgoing_links": 6},
            {"depth": 1, "pages": 2, "fetched_pages": 2, "outgoing_links": 4},
            {"depth": 2, "pages": 3, "fetched_pages": 3, "outgoing_links": 1},
            {"depth": 3, "pages": 1, "fetched_pages": 1, "outgoing_links": 0},
        ]
        assert len(stats["per_page"]) == 7
        assert all("body" not in node and "description" not in node for node in graph["nodes"])
    with TestClient(create_app(settings)) as client:
        assert client.get(path + "/graph").json() == graph
        assert client.get(path + "/stats").json() == stats


def test_21_pages_three_levels_and_page_limit_depth_semantics(database):
    pages = {"/": "".join(f'<a href="/{i}">{i}</a>' for i in range(1, 8))}
    for i in range(1, 8):
        pages[f"/{i}"] = f'<a href="/{i}/a">child</a>'
        pages[f"/{i}/a"] = f'<a href="/{i}/a/end">end</a>' if i < 7 else "leaf"
        if i < 7:
            pages[f"/{i}/a/end"] = '<a href="/">cycle</a>'
    assert len(pages) == 21
    settings, _ = database
    with (
        website(pages) as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        session_id = create(client)
        client.post(f"/api/sessions/{session_id}/start")
        assert finished(client, session_id)["fetched_count"] == 21
        graph = client.get(f"/api/sessions/{session_id}/graph").json()
        assert_graph_invariants(graph)
        assert graph["summary"]["reached_depth"] == 3
        assert graph["summary"]["page_count"] == 21
        assert graph["summary"]["link_count"] == 26
        small = create(client, max_pages=1)
        client.post(f"/api/sessions/{small}/start")
        finished(client, small)
        summary = client.get(f"/api/sessions/{small}/stats").json()["summary"]
        assert summary["reached_depth"] == 0 and summary["discovered_depth"] == 1
        assert summary["fetched_pages"] == 1 and summary["page_count"] == 8


def test_self_loops_external_errors_and_target_url_shared_by_asset_and_page(database):
    settings, _ = database
    pages = {
        "/": '<a href="/">self</a><a href="/bad">bad</a><img src="/bad">'
        '<a href="http://other.example/out">external</a><img src="http://other.example/x.png">',
        "/bad": (500, {}, "error"),
    }
    with (
        website(pages) as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        session_id = create(client, link_types="all_links")
        path = f"/api/sessions/{session_id}"
        client.post(path + "/start")
        finished(client, session_id)
        graph = client.get(path + "/graph").json()
        assert_graph_invariants(graph)
        summary = graph["summary"]
        assert (
            summary["node_count"],
            summary["page_count"],
            summary["link_count"],
            summary["unique_relations"],
        ) == (4, 3, 5, 4)
        assert summary["external_links"] == 2 and summary["internal_links"] == 3
        assert summary["errored_pages"] == 1 and summary["reached_depth"] == 0
        root = next(node for node in graph["nodes"] if node["depth"] == 0)
        assert root["in_degree"] == root["unique_in_degree"] == 1
        bad = next(node for node in graph["nodes"] if node["url"] == ROOT + "/bad")
        assert bad["in_degree"] == 2 and bad["unique_in_degree"] == 1 and not bad["fetched"]
        external = next(node for node in graph["nodes"] if node["url"].endswith("/out"))
        assert not external["fetched"] and external["page_id"] is not None


def test_empty_validation_isolation_and_explicit_visualization_limit(client, monkeypatch):
    first, second = create(client), create(client)
    path = f"/api/sessions/{first}"
    graph = client.get(path + "/graph").json()
    assert graph["nodes"] == graph["edges"] == []
    assert graph["summary"]["reached_depth"] is None
    assert client.get(path + "/stats").json()["per_page"] == []
    with Session(client.app.state.engine) as db:
        page = Page(
            session_id=first,
            normalized_url=ROOT + "/",
            original_url=ROOT + "/",
            depth=0,
            discovery_order=0,
            title="x" * 600,
        )
        db.add(page)
        db.flush()
        db.add(
            Link(
                session_id=first,
                source_page_id=page.id,
                target_url=ROOT + "/x.png",
                kind=LinkKind.IMAGE,
            )
        )
        db.commit()
    graph = client.get(path + "/graph").json()
    assert len(graph["nodes"][0]["title"]) == 500
    assert client.get(f"/api/sessions/{second}/graph").json()["nodes"] == []
    monkeypatch.setattr(api, "MAX_GRAPH_NODES", 1)
    assert client.get(path + "/graph").status_code == 413
    assert client.get(path + "/stats").json()["summary"]["node_count"] == 2
    monkeypatch.setattr(api, "MAX_GRAPH_NODES", 10)
    monkeypatch.setattr(api, "MAX_GRAPH_EDGES", 0)
    assert client.get(path + "/graph").status_code == 413
    assert client.get(path + "/stats").json()["summary"]["link_count"] == 1
    for endpoint in ["graph", "stats"]:
        assert client.get(f"/api/sessions/{uuid4()}/{endpoint}").status_code == 404
        assert client.get(f"/api/sessions/invalid/{endpoint}").status_code == 422
    assert client.delete(path).status_code == 204
    assert client.get(path + "/graph").status_code == 404
