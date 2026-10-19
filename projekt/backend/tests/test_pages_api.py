from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from test_sessions import create

from app.models import Link, LinkKind, Page


def test_empty_pages_and_session_scoping(client):
    first, second = create(client), create(client)
    path = f"/api/sessions/{first['id']}/pages"
    assert client.get(path).json() == {"items": [], "total": 0, "offset": 0, "limit": 20}
    with Session(client.app.state.engine) as db:
        page = Page(
            session_id=first["id"],
            normalized_url="https://example.com/",
            original_url="https://example.com/",
            depth=0,
            discovery_order=0,
            title="<script>alert(1)</script>",
            body="untrusted <b>text</b>",
        )
        db.add(page)
        db.flush()
        page_id = page.id
        for _ in range(3):
            db.add(
                Link(
                    session_id=first["id"],
                    source_page_id=page_id,
                    target_url="https://example.org/",
                    kind=LinkKind.HYPERLINK,
                    is_external=True,
                    is_followed=False,
                )
            )
        db.commit()
    detail = f"{path}/{page_id}"
    assert client.get(detail).json()["title"] == "<script>alert(1)</script>"
    assert client.get(detail).json()["body"] == "untrusted <b>text</b>"
    links = client.get(detail + "/links?limit=2").json()
    next_page = client.get(detail + "/links?offset=2&limit=2").json()
    assert links["total"] == next_page["total"] == 3
    assert len(links["items"]) == 2 and len(next_page["items"]) == 1
    assert len({link["id"] for link in links["items"] + next_page["items"]}) == 3
    assert client.get(path + "?offset=100").json()["items"] == []
    for suffix in ["", "/links"]:
        response = client.get(f"/api/sessions/{second['id']}/pages/{page_id}" + suffix)
        assert response.status_code == 404 and response.json()["code"] == "page_not_found"
        assert client.get(f"/api/sessions/{uuid4()}/pages/{page_id}" + suffix).status_code == 404
        assert client.get(f"{path}/{uuid4()}" + suffix).status_code == 404
    assert client.get(f"/api/sessions/{uuid4()}/pages").status_code == 404
    assert client.delete(f"/api/sessions/{first['id']}").status_code == 204
    assert client.get(detail + "/links").status_code == 404


@pytest.mark.parametrize(
    "query", ["offset=-1", "offset=2147483648", "limit=0", "limit=101", "limit=x", "offset=x"]
)
def test_page_pagination_validation(client, query):
    session = create(client)
    path = f"/api/sessions/{session['id']}/pages"
    assert client.get(path + "?" + query).status_code == 422
    assert client.get(path + f"/{uuid4()}/links?" + query).status_code == 422


def test_page_uuid_validation(client):
    session = create(client)
    assert client.get("/api/sessions/bad/pages").status_code == 422
    path = f"/api/sessions/{session['id']}/pages/bad"
    assert client.get(path).status_code == 422
    assert client.get(path + "/links").status_code == 422
