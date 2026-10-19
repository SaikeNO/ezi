import csv
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_sessions import create

from app import explorer
from app.explorer import safe_cell
from app.main import create_app
from app.models import Page


@pytest.fixture
def dataset(client):
    session_id = create(client)["id"]
    other = create(client)["id"]
    with Session(client.app.state.engine) as db:
        for index in range(13):
            db.add(
                Page(
                    session_id=session_id,
                    normalized_url=f"https://example.com/{index}",
                    original_url=f"https://example.com/{index}",
                    depth=index % 3,
                    discovery_order=index,
                    final_url=f"https://example.com/{index}" if index < 10 else None,
                    http_status=200 if index < 10 else 500 if index == 10 else None,
                    content_type="text/html" if index < 10 else None,
                    encoding="utf-8" if index < 10 else None,
                    title='ŁÓDŹ, "żółw";\r\nDrugi wiersz' if index == 0 else f"Page {index}",
                    description="100%_literal" if index == 1 else None,
                    keywords='=HYPERLINK("https://bad.example")' if index == 0 else "żółć",
                    body='Zażółć, "gęślą";\tjaźń\nNowa linia\r\nKoniec' if index == 0 else None,
                    error="http_error" if index == 10 else None,
                )
            )
        db.add(
            Page(
                session_id=other,
                normalized_url="https://example.org/",
                original_url="x",
                depth=0,
                discovery_order=0,
                title="ŁÓDŹ private",
            )
        )
        db.commit()
    return session_id, other


def csv_rows(response, delimiter=","):
    assert response.status_code == 200, response.text
    return list(
        csv.reader(
            io.StringIO(response.content.decode("utf-8-sig"), newline=""), delimiter=delimiter
        )
    )


@pytest.mark.parametrize("separator,delimiter", [("comma", ","), ("semicolon", ";"), ("tab", "\t")])
@pytest.mark.parametrize("bom", [True, False])
def test_csv_round_trip_fields_order_unicode_quotes_newlines(
    client, dataset, separator, delimiter, bom
):
    session_id, _ = dataset
    response = client.get(
        f"/api/sessions/{session_id}/export",
        params={
            "fields": "body,title,keywords,url,http_status",
            "separator": separator,
            "bom": str(bom).lower(),
        },
    )
    assert response.content.startswith(b"\xef\xbb\xbf") is bom
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert (
        response.headers["content-disposition"] == f'attachment; filename="crawl-{session_id}.csv"'
    )
    assert int(response.headers["content-length"]) == len(response.content)
    rows = csv_rows(response, delimiter)
    assert rows[0] == ["Body", "Title", "Keyword", "URL", "HTTP Status"]
    assert len(rows) == 14
    assert rows[1] == [
        'Zażółć, "gęślą";\tjaźń\nNowa linia\r\nKoniec',
        'ŁÓDŹ, "żółw";\r\nDrugi wiersz',
        '\'=HYPERLINK("https://bad.example")',
        "https://example.com/0",
        "200",
    ]
    assert rows[-1][0] == "" and rows[-1][-1] == ""


@pytest.mark.parametrize(
    "value",
    [
        "=1+1",
        "+cmd",
        "-1+2",
        "@SUM(A1)",
        " \t=1",
        "\r=1",
        "\n+1",
        "\ttext",
        "\ufeff=1",
        "\u200b @A1",
        "\ufeff \u200b\t=1",
        "＝1",
        "＋1",
        "－1",
        "＠1",
    ],
)
def test_formula_cells_become_text_without_losing_original(value):
    assert safe_cell(value) == "'" + value


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, ""),
        (200, "200"),
        ("żółw", "żółw"),
        ("hello =1", "hello =1"),
        ("'text", "'text"),
        ('a,"=1",b', 'a,"=1",b'),
    ],
)
def test_safe_values_preserved(value, expected):
    assert safe_cell(value) == expected


@pytest.mark.parametrize(
    "filters,count",
    [
        ({"q": "łódź"}, 1),
        ({"q": "%_"}, 1),
        ({"q": "x' OR 1=1 --"}, 0),
        ({"depth": 2}, 4),
        ({"fetched": "true"}, 10),
        ({"fetched": "false"}, 3),
        ({"has_error": "true"}, 1),
        ({"has_error": "false"}, 12),
        ({"http_status": 500}, 1),
        ({"fetched": "false", "has_error": "true", "depth": 1}, 1),
    ],
)
def test_same_filters_for_list_and_full_export(client, dataset, filters, count):
    session_id, _ = dataset
    base = f"/api/sessions/{session_id}"
    listing = client.get(base + "/pages", params={**filters, "limit": 100}).json()
    rows = csv_rows(client.get(base + "/export", params={**filters, "fields": "url"}))
    assert listing["total"] == count and len(rows) == count + 1
    assert [row[0] for row in rows[1:]] == [row["normalized_url"] for row in listing["items"]]


def test_pagination_and_whole_export_empty_headers(client, dataset):
    session_id, other = dataset
    base = f"/api/sessions/{session_id}"
    first = client.get(base + "/pages?limit=10").json()
    second = client.get(base + "/pages?limit=10&offset=10").json()
    assert len(first["items"]) == 10 and len(second["items"]) == 3
    assert len(csv_rows(client.get(base + "/export"))) == 14
    empty = create(client)["id"]
    assert csv_rows(client.get(f"/api/sessions/{empty}/export")) == [["URL", "Keyword"]]
    assert len(csv_rows(client.get(f"/api/sessions/{other}/export"))) == 2
    assert "body" not in first["items"][0]


def test_remaining_export_columns_are_stored_values(client, dataset):
    session_id, _ = dataset
    rows = csv_rows(
        client.get(
            f"/api/sessions/{session_id}/export",
            params={
                "fields": "error,depth,final_url,description,original_url,content_type,encoding"
            },
        )
    )
    assert rows[0] == [
        "Error",
        "Depth",
        "Final URL",
        "Description",
        "Original URL",
        "Content-Type",
        "Encoding",
    ]
    assert rows[1] == [
        "",
        "0",
        "https://example.com/0",
        "",
        "https://example.com/0",
        "text/html",
        "utf-8",
    ]
    assert rows[11] == ["http_error", "1", "", "", "https://example.com/10", "", ""]


@pytest.mark.parametrize(
    "query",
    [
        "fields=",
        "fields=url,url",
        "fields=bad",
        "fields=url,,title",
        "separator=pipe",
        "bom=maybe",
        "depth=-1",
        "depth=22",
        "http_status=99",
        "http_status=600",
        "fetched=maybe",
        "has_error=maybe",
        "q=" + "a" * 201,
    ],
)
def test_validation_export_and_filters(client, query):
    session_id = create(client)["id"]
    assert client.get(f"/api/sessions/{session_id}/export?{query}").status_code == 422
    if query.startswith(("depth=", "http_status=", "fetched=", "has_error=", "q=")):
        assert client.get(f"/api/sessions/{session_id}/pages?{query}").status_code == 422


def test_export_cap_no_partial_download_and_unknown_sessions(client, dataset, monkeypatch):
    session_id, _ = dataset
    monkeypatch.setattr(explorer, "MAX_EXPORT_BYTES", 20)
    response = client.get(f"/api/sessions/{session_id}/export")
    assert response.status_code == 413 and response.json()["code"] == "export_too_large"
    monkeypatch.setattr(explorer, "MAX_EXPORT_BYTES", 999999)
    monkeypatch.setattr(explorer, "MAX_EXPORT_SECONDS", -1)
    assert client.get(f"/api/sessions/{session_id}/export").status_code == 503
    assert client.get(f"/api/sessions/{uuid4()}/export").status_code == 404
    assert client.get("/api/sessions/not-a-uuid/export").status_code == 422


def test_export_snapshot_survives_app_restart(database):
    settings, _ = database
    with TestClient(create_app(settings)) as client:
        session_id = create(client)["id"]
        path = f"/api/sessions/{session_id}/export"
        with Session(client.app.state.engine) as db:
            db.add(
                Page(
                    session_id=session_id,
                    normalized_url="https://example.com/",
                    original_url="x",
                    depth=0,
                    discovery_order=0,
                    keywords="Łódź",
                )
            )
            db.commit()
        before = client.get(path).content
    with TestClient(create_app(settings)) as client:
        assert client.get(path).content == before
