import codecs
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from site_fixture import ROOT, website
from test_crawler_engine import create, finished

from app.crawler.discovery import extract
from app.main import create_app
from app.models import LinkKind, LinkSelection

FIXTURE = (Path(__file__).parent / "fixtures" / "extraction.html").read_bytes()
URL = ROOT + "/docs/index.html"


@pytest.mark.parametrize(
    "mode,count",
    [
        (LinkSelection.HYPERLINKS, 5),
        (LinkSelection.IMAGES_AND_HYPERLINKS, 6),
        (LinkSelection.ALL_LINKS, 18),
    ],
)
def test_fixture_metadata_and_modes(mode, count):
    result = extract(FIXTURE, URL, mode)
    assert result.url == URL and result.encoding == "utf-8"
    assert result.title == "Zażółć & gęślą"
    assert result.description == "Polski & opis"
    assert result.keywords == "żółw, Łódź, WWW"
    assert result.body.startswith("Treść <HTML> Polski tekst.")
    assert all(word not in result.body for word in ["throw", "display", "hidden", "Zażółć"])
    assert len(result.references) == count
    hyperlinks = [ref.url for ref in result.references if ref.kind == LinkKind.HYPERLINK]
    assert hyperlinks == [
        ROOT + "/assets/page",
        ROOT + "/map",
        ROOT + "/assets/page",
        "https://other.example/out",
        "http://cdn.example/file",
    ]
    if mode == LinkSelection.ALL_LINKS:
        assert {ref.kind for ref in result.references} == set(LinkKind)
        assert result.references[0].url == ROOT + "/assets/theme.css"


@pytest.mark.parametrize(
    "base,expected",
    [
        ('<base href="/root/">', ROOT + "/root/next"),
        ('<base href="https://other.example/dir/">', "https://other.example/dir/next"),
        ('<base href="javascript:bad"><base href="/ignored/">', ROOT + "/docs/next"),
        ("", ROOT + "/docs/next"),
        ('<base href=""><base href="/ignored/">', ROOT + "/docs/next"),
    ],
)
def test_base_resolution(base, expected):
    result = extract((base + '<a href="next#x">').encode(), URL, LinkSelection.HYPERLINKS)
    assert result.references[0].url == expected


@pytest.mark.parametrize(
    "data,header,expected_encoding",
    [
        ('<meta charset="windows-1250"><title>Łódź</title>'.encode("cp1250"), None, "cp1250"),
        (
            '<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-2">'
            "<title>Łódź</title>".encode("iso8859-2"),
            None,
            "iso8859-2",
        ),
        ('<meta charset="utf-8"><title>Łódź</title>'.encode("cp1250"), "windows-1250", "cp1250"),
        (
            '<meta charset="windows-1250"><title>Łódź</title>'.encode("utf-8-sig"),
            "cp1250",
            "utf-8-sig",
        ),
        ("<title>Łódź</title>".encode("utf-16"), "utf-8", "utf-16"),
        ("<title>Łódź</title>".encode("utf-32"), None, "utf-32"),
        ('<meta charset="utf-8"><title>Łódź</title>'.encode(), "not-an-encoding", "utf-8"),
        ("<title>Łódź</title>".encode(), "base64", "utf-8"),
    ],
)
def test_encoding_precedence(data, header, expected_encoding):
    result = extract(data, URL, LinkSelection.HYPERLINKS, header)
    assert result.title == "Łódź" and result.encoding == expected_encoding


def test_bad_bytes_missing_empty_fields_and_malformed_html():
    result = extract(
        b'<meta name="description" content=""><title>Bad\xff</title>'
        b"<body><h1>One<p>Two &amp; three<a href=next>Go",
        URL,
        LinkSelection.HYPERLINKS,
    )
    assert result.title == "Bad\ufffd"
    assert result.description == "" and result.keywords is None
    assert result.body == "One Two & threeGo"
    assert result.references[0].url == ROOT + "/docs/next"
    missing = extract(b"<p>fragment<b>text</b><br>end", URL, LinkSelection.HYPERLINKS)
    assert missing.title is None and missing.description is None and missing.keywords is None
    assert missing.body == "fragmenttext end"
    assert extract(b"", URL, LinkSelection.HYPERLINKS).body == ""


def test_stream_boundaries_do_not_change_words_or_entities():
    text = "a" * 8190 + "&amp;" + "b" * 9000
    result = extract(text.encode(), URL, LinkSelection.HYPERLINKS)
    assert result.body == "a" * 8190 + "&" + "b" * 9000


@pytest.mark.parametrize(
    "content_type,declaration",
    [
        ("text/html; charset=windows-1250", ""),
        ("text/html", '<meta charset="windows-1250">'),
        ("application/xhtml+xml", '<meta charset="windows-1250"/>'),
    ],
)
def test_http_charset_and_meta_survive_fetcher(database, content_type, declaration):
    settings, _ = database
    html = (declaration + "<title>Łódź</title><body>Zażółć</body>").encode("cp1250")
    with (
        website({"/": (200, {"Content-Type": content_type}, html)}) as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        session_id = create(client, process_one_page=True)
        client.post(f"/api/sessions/{session_id}/start")
        assert finished(client, session_id)["error_count"] == 0
        path = f"/api/sessions/{session_id}/pages"
        page_id = client.get(path).json()["items"][0]["id"]
        result = client.get(path + "/" + page_id).json()
        assert result["title"] == "Łódź" and result["body"] == "Zażółć"
        assert result["encoding"] == "cp1250"
        assert result["content_type"] == content_type.split(";")[0]


@pytest.mark.parametrize(
    "mode,count", [("hyperlinks", 5), ("images_and_hyperlinks", 6), ("all_links", 18)]
)
def test_crawl_persists_metadata_and_links_exposes_api_after_restart(database, mode, count):
    settings, _ = database
    html = codecs.BOM_UTF8 + FIXTURE
    pages = {
        "/": (302, {"Location": "/docs/index.html"}, ""),
        "/docs/index.html": (200, {"Content-Type": "text/html; charset=cp1250"}, html),
    }
    with (
        website(pages) as site,
        TestClient(create_app(settings, transport_factory=site.transport)) as client,
    ):
        session_id = create(client, link_types=mode, process_one_page=True)
        client.post(f"/api/sessions/{session_id}/start")
        state = finished(client, session_id)
        assert state["status"] == "completed" and state["error_count"] == 0
        assert state["link_count"] == count and state["fetched_count"] == 1
        path = f"/api/sessions/{session_id}/pages"
        listing = client.get(path + "?limit=1").json()
        assert listing["total"] == 5  # start + four unique hyperlink destinations
        first = listing["items"][0]
        assert "body" not in first
        detail_path = path + "/" + first["id"]
        detail = client.get(detail_path).json()
        assert detail["title"] == "Zażółć & gęślą"
        assert detail["description"] == "Polski & opis"
        assert detail["keywords"] == "żółw, Łódź, WWW"
        assert detail["normalized_url"] == ROOT + "/"
        assert detail["final_url"] == URL and detail["http_status"] == 200
        assert detail["content_type"] == "text/html" and detail["encoding"] == "utf-8-sig"
        assert detail["body"].startswith("Treść <HTML> Polski tekst.")
        links = client.get(detail_path + "/links?limit=100").json()
        assert links["total"] == count and len(links["items"]) == count
        assert sum(link["target_url"] == ROOT + "/assets/page" for link in links["items"]) == 2
        assert all(not link["is_followed"] for link in links["items"])
        assert [path for path, _, _ in site.requests] == ["/robots.txt", "/", "/docs/index.html"]
    with TestClient(create_app(settings)) as client:
        assert client.get(detail_path).json() == detail
        assert client.get(detail_path + "/links?limit=100").json() == links
        second = client.get(path + "?offset=1&limit=1").json()["items"][0]
        assert client.get(path + "/" + second["id"]).json()["body"] is None
        assert client.delete(f"/api/sessions/{session_id}").status_code == 204
        assert client.get(detail_path).status_code == 404
