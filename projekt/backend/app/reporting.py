"""Read-only laboratory reports. Untrusted values are always escaped text."""

import json
from datetime import UTC, datetime
from html import escape
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api import Database, find_session
from app.comparison import CompareInput, compare
from app.graph import MAX_GRAPH_EDGES, MAX_GRAPH_NODES, projection
from app.models import CrawlSession, Link, Page, SessionStatus
from app.schemas import ErrorResponse, SessionRead

router = APIRouter(
    prefix="/api",
    tags=["reports"],
    responses={status: {"model": ErrorResponse} for status in (404, 409, 413, 422, 503)},
)


class DashboardRead(BaseModel):
    sessions: int
    statuses: dict[SessionStatus, int]
    discovered_pages: int
    fetched_pages: int
    errored_pages: int
    links: int
    recent: list[SessionRead]


@router.get("/dashboard", response_model=DashboardRead)
def dashboard(db: Database) -> DashboardRead:
    db.connection().exec_driver_sql("BEGIN")
    statuses = dict.fromkeys(SessionStatus, 0)
    statuses.update(
        dict(
            db.execute(
                select(CrawlSession.status, func.count()).group_by(CrawlSession.status)
            ).all()
        )
    )

    def count(model, *conditions):
        return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0

    recent = db.scalars(
        select(CrawlSession)
        .order_by(CrawlSession.created_at.desc(), CrawlSession.id.desc())
        .limit(5)
    ).all()
    return DashboardRead(
        sessions=sum(statuses.values()),
        statuses=statuses,
        discovered_pages=count(Page),
        fetched_pages=count(Page, Page.final_url.is_not(None)),
        errored_pages=count(Page, Page.error.is_not(None)),
        links=count(Link),
        recent=[SessionRead.model_validate(row) for row in recent],
    )


def text(value) -> str:
    return escape("brak" if value is None else str(value), quote=True)


def table(headers, rows) -> str:
    return (
        '<div class="table-scroll" tabindex="0" aria-label="Tabela raportu — przewiń poziomo">'
        "<table><thead><tr>"
        + "".join(f"<th>{text(h)}</th>" for h in headers)
        + (
            "</tr></thead><tbody>"
            + "".join(
                "<tr>" + "".join(f"<td>{text(value)}</td>" for value in row) + "</tr>"
                for row in rows
            )
            + "</tbody></table></div>"
        )
    )


def document(title: str, content: str, filename: str) -> HTMLResponse:
    html = f"""<!doctype html><html lang="pl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{text(title)}</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem;color:#132b32}}
.table-scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;min-width:620px;
margin:1rem 0}}h3{{overflow-wrap:anywhere}}th,td{{border:1px solid #aaa;
padding:.5rem;text-align:left;overflow-wrap:anywhere}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
@media print{{body{{margin:0;font-size:10pt}}table{{min-width:0}}
.table-scroll{{overflow:visible}}thead{{display:table-header-group}}}}</style>
<h1>{text(title)}</h1><p>Wygenerowano UTC: {datetime.now(UTC).isoformat()}</p>
{content}</html>"""
    return HTMLResponse(
        html,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.html"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        },
    )


INTERPRETATION = """<h2>Interpretacja i zastosowania (I.4, II.6, II.8)</h2>
<p>URL identyfikuje rekord i umożliwia analizę nawigacji; Keyword pomaga w indeksowaniu
tematycznym, lecz brak lub puste słowa kluczowe wymagają analizy title, description i body.
Schemat danych: URL, Title, Keyword, Description, Body, Depth, HTTP Status i błąd.
CSV URL/Keyword jest przydatny jako prosty indeks; graf zachowuje relacje, których CSV
stron nie odtwarza. Null i pusty tekst są odrębne w bazie, identyczne w CSV.</p>
<p>Praktyczny wybór zależy od celu: server ogranicza host, web z follow_external_urls
poszerza zakres; hyperlinks opisuje nawigację, all_links także zasoby. Większa głębokość
zwiększa możliwy zakres i koszt. Zestaw pobranych HTML i błędy należy ocenić przed wyborem.
Raport nie wybiera automatycznie najlepszego wariantu. BFS/DFS steruje kolejnością;
pełny graf może być taki sam. Czas obejmuje sieć, robots, opóźnienia i analizę.</p>"""


@router.get("/sessions/{session_id}/report", response_class=HTMLResponse)
def session_report(session_id: UUID, db: Database) -> HTMLResponse:
    _, stats = projection(
        db, session_id, graph_limits=(MAX_GRAPH_NODES, MAX_GRAPH_EDGES), include_edges=False
    )
    run = SessionRead.model_validate(find_session(db, session_id))
    elapsed = (
        (run.finished_at - run.started_at).total_seconds()
        if run.finished_at and run.started_at
        else None
    )
    coverage = db.execute(
        select(
            *[
                func.count(getattr(Page, field))
                for field in ("title", "keywords", "description", "body")
            ]
        ).where(Page.session_id == str(session_id), Page.final_url.is_not(None))
    ).one()
    content = f"<p>Sesja: {text(run.id)}; URL: {text(run.start_url)}</p>"
    content += f"<p>Status: {text(run.status.value)}; stop_reason: {text(run.stop_reason)}; "
    content += f"czas (s): {text(elapsed if elapsed is None or elapsed >= 0 else None)}</p>"
    if (
        run.status != SessionStatus.COMPLETED
        or run.stop_reason != "frontier_exhausted"
        or stats.summary.errored_pages
    ):
        content += (
            "<p>Wyniki częściowe, oczekujące, z limitem lub błędami. "
            "Brak URL nie dowodzi nieosiągalności.</p>"
        )
    content += (
        f"<p>Błąd sesji: {text(run.error)}; crawler: {text(run.crawler_version)}; "
        f"User-Agent: {text(run.user_agent)}</p>"
    )
    content += (
        "<h2>Konfiguracja (I.2, II.5, II.7)</h2><pre>"
        + text(json.dumps(run.config.model_dump(mode="json"), ensure_ascii=False, indent=2))
        + "</pre><h2>Struktura i liczniki (I.1)</h2>"
    )
    content += table(["Metryka", "Wartość"], stats.summary.model_dump().items())
    content += "<h2>Poziomy (start = 0)</h2>" + table(
        ["Depth", "Odkryte", "Pobrane HTML", "Linki"],
        [(d.depth, d.pages, d.fetched_pages, d.outgoing_links) for d in stats.per_depth],
    )
    content += "<h2>Metadane obecne w pobranych HTML</h2>" + table(
        ["Pole", "Obecne (w tym puste)", "Brak"],
        [
            (field, count, stats.summary.fetched_pages - count)
            for field, count in zip(
                ("Title", "Keyword", "Description", "Body"), coverage, strict=True
            )
        ],
    )
    content += "<h2>Stopnie stron</h2>" + table(
        ["URL", "Depth", "Pobrana", "In", "Out", "Unique in", "Unique out"],
        [
            (
                p.url,
                p.depth,
                p.fetched,
                p.in_degree,
                p.out_degree,
                p.unique_in_degree,
                p.unique_out_degree,
            )
            for p in stats.per_page
        ],
    )
    content += (
        INTERPRETATION
        + "<p>I.3 i II.8: użyj raportu porównania co najmniej dwóch sesji tego samego URL.</p>"
    )
    return document("Raport sesji — WebCrawler Studio", content, f"report-{session_id}")


@router.post("/reports/compare", response_class=HTMLResponse)
def comparison_report(payload: CompareInput, db: Database) -> HTMLResponse:
    result = compare(db, payload.session_ids, 0, 100)
    content = f"<p>Start URL: {text(result.start_url)}</p><h2>Warianty (I.2, I.3, II.7)</h2>"
    content += table(
        ["ID", "Status", "Stop", "Odkryte", "HTML", "Linki", "Depth", "Błędy", "Sekundy"],
        [
            (
                r.session.id,
                r.session.status.value,
                r.session.stop_reason,
                r.discovered_pages,
                r.fetched_pages,
                r.link_count,
                r.reached_depth,
                r.errored_pages,
                r.elapsed_seconds,
            )
            for r in result.runs
        ],
    )
    for run in result.runs:
        content += table(
            ["Sesja", "Start UTC", "Koniec UTC", "Crawler", "User-Agent"],
            [
                (
                    run.session.id,
                    run.session.started_at,
                    run.session.finished_at,
                    run.session.crawler_version,
                    run.session.user_agent,
                )
            ],
        )
        content += (
            f"<h3>Konfiguracja {text(run.session.id)}</h3><pre>"
            + text(
                json.dumps(run.session.config.model_dump(mode="json"), ensure_ascii=False, indent=2)
            )
            + "</pre>"
        )
        content += table(["Pole metadanych", "Obecne (w tym puste)"], run.metadata_present.items())
    content += (
        "<h2>Różnice (I.3, II.8)</h2><p>Listy: pierwsze maksymalnie 100 elementów "
        "każdej kategorii; total obejmuje całość. Pełne partie: POST /api/compare "
        "(offset/limit). Podgląd treści: 500 znaków; SHA-256 obejmuje całość.</p>"
    )
    for pair in result.pairs:
        content += f"<h3>{text(pair.left_id)} względem {text(pair.right_id)}</h3>"
        content += table(
            ["Zbiór", "Wspólne", "Tylko A", "Tylko B"],
            [
                (label, values.common.total, values.left_only.total, values.right_only.total)
                for label, values in (
                    ("Odkryte URL", pair.discovered),
                    ("Pobrane HTML", pair.fetched),
                    ("Typowane krawędzie", pair.edges),
                )
            ],
        )
        content += "".join(f"<p>{text(observation)}</p>" for observation in pair.observations)
        content += table(
            ["Parametr", "A", "B"], [(key, *values) for key, values in pair.config_changes.items()]
        )
        content += "<details><summary>Szczegóły zbiorów i treści (JSON)</summary>"
        content += (
            "<pre>"
            + text(json.dumps(pair.model_dump(mode="json"), ensure_ascii=False, indent=2))
            + "</pre>"
        )
        content += "</details>"
    content += "<h2>Ograniczenia pomiaru</h2>" + "".join(
        f"<p>{text(note)}</p>" for note in result.notes
    )
    return document(
        "Raport porównania — WebCrawler Studio", content + INTERPRETATION, "comparison-report"
    )
