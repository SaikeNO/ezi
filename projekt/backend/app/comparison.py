"""Bounded comparison of saved results in one read transaction."""

import time
from collections import Counter
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CrawlSession, Link, LinkKind, Page, SessionStatus
from app.schemas import InputModel, SessionRead

MAX_COMPARE_PAGES = 20000
MAX_COMPARE_LINKS = 80000
MAX_COMPARE_TEXT_BYTES = 64 * 1024 * 1024
MAX_COMPARE_SECONDS = 30
CONTENT_FIELDS = ("title", "description", "keywords", "body")


class CompareInput(InputModel):
    session_ids: Annotated[list[UUID], Field(min_length=2, max_length=4)]

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.session_ids)) != len(self.session_ids):
            raise ValueError("Select distinct sessions")
        return self


class ResultList[T](BaseModel):
    items: list[T]
    total: int
    offset: int
    limit: int


class TextValue(BaseModel):
    value: str | None
    length: int | None
    sha256: str | None
    truncated: bool


class ContentChange(BaseModel):
    url: str
    fields: dict[str, list[TextValue]]  # Ordered A then B; null and empty remain distinct.


class EdgeKey(BaseModel):
    source: str
    target: str
    kind: LinkKind


class EdgeChange(EdgeKey):
    left_count: int
    right_count: int


class DepthChange(BaseModel):
    url: str
    left: int
    right: int


class UrlSets(BaseModel):
    common: ResultList[str]
    left_only: ResultList[str]
    right_only: ResultList[str]


class EdgeSets(BaseModel):
    common: ResultList[EdgeKey]
    left_only: ResultList[EdgeKey]
    right_only: ResultList[EdgeKey]
    multiplicity_changes: ResultList[EdgeChange]


class RunMetrics(BaseModel):
    session: SessionRead
    discovered_pages: int
    fetched_pages: int
    attempted_pages: int
    errored_pages: int
    link_count: int
    unique_typed_edges: int
    reached_depth: int | None
    elapsed_seconds: float | None
    metadata_present: dict[str, int]
    retrieval_order: ResultList[str]


class PairComparison(BaseModel):
    left_id: UUID
    right_id: UUID
    config_changes: dict[str, list[str | int | float | bool]]
    discovered: UrlSets
    fetched: UrlSets
    edges: EdgeSets
    metadata_changes: ResultList[ContentChange]
    depth_changes: ResultList[DepthChange]
    retrieval_order_equal: bool
    observations: list[str]


class ComparisonRead(BaseModel):
    start_url: str
    runs: list[RunMetrics]
    pairs: list[PairComparison]
    notes: list[str]


def compare(db: Session, ids: list[UUID], offset: int, limit: int) -> ComparisonRead:
    db.connection().exec_driver_sql("BEGIN")
    deadline = time.monotonic() + MAX_COMPARE_SECONDS
    sessions = [db.get(CrawlSession, str(session_id)) for session_id in ids]
    if any(run is None for run in sessions):
        raise HTTPException(
            404, detail={"code": "session_not_found", "message": "Nie znaleziono sesji"}
        )
    if len({run.start_url for run in sessions}) != 1:
        raise HTTPException(
            409,
            detail={
                "code": "different_start_urls",
                "message": "Wybierz sesje z identycznym znormalizowanym adresem startowym",
            },
        )
    if any(run.status in {SessionStatus.QUEUED, SessionStatus.RUNNING} for run in sessions):
        raise HTTPException(
            409,
            detail={
                "code": "comparison_not_ready",
                "message": "Poczekaj na zakończenie lub anuluj wybrane sesje",
            },
        )
    filters = [Page.session_id.in_([str(value) for value in ids])]
    page_count = db.scalar(select(func.count()).select_from(Page).where(*filters)) or 0
    link_count = (
        db.scalar(
            select(func.count())
            .select_from(Link)
            .where(Link.session_id.in_([str(value) for value in ids]))
        )
        or 0
    )
    if page_count > MAX_COMPARE_PAGES or link_count > MAX_COMPARE_LINKS:
        raise HTTPException(
            413,
            detail={
                "code": "comparison_too_large",
                "message": "Porównanie przekracza limit 20000 stron lub 80000 linków",
            },
        )

    def result(values):
        return {
            "items": values[offset : offset + limit],
            "total": len(values),
            "offset": offset,
            "limit": limit,
        }

    def url_sets(left, right):
        return UrlSets(
            common=result(sorted(left & right)),
            left_only=result(sorted(left - right)),
            right_only=result(sorted(right - left)),
        )

    pages_by_run = []
    edges_by_run = []
    metrics = []
    orders = []
    text_bytes = 0
    for run in sessions:
        pages = {}
        page_urls = {}
        attempted = []
        present = dict.fromkeys(CONTENT_FIELDS, 0)
        error_count = 0
        for row in db.execute(
            select(
                Page.id,
                Page.normalized_url,
                Page.depth,
                Page.fetch_order,
                Page.final_url,
                Page.error,
                Page.title,
                Page.description,
                Page.keywords,
                Page.body,
            )
            .where(Page.session_id == run.id)
            .order_by(Page.discovery_order, Page.id)
        ).yield_per(1):
            values = {}
            for field in CONTENT_FIELDS:
                value = getattr(row, field)
                encoded = value.encode("utf-8") if value is not None else b""
                text_bytes += len(encoded)
                if text_bytes > MAX_COMPARE_TEXT_BYTES:
                    raise HTTPException(
                        413,
                        detail={
                            "code": "comparison_too_large",
                            "message": "Limit treści: 64 MiB. Wybierz mniejsze sesje.",
                        },
                    )
                values[field] = TextValue(
                    value=value[:500] if value is not None else None,
                    length=len(value) if value is not None else None,
                    sha256=sha256(encoded).hexdigest() if value is not None else None,
                    truncated=value is not None and len(value) > 500,
                )
                present[field] += int(value is not None)
            if time.monotonic() > deadline:
                raise HTTPException(
                    503,
                    detail={
                        "code": "comparison_timeout",
                        "message": "Przekroczono czas porównania. Wybierz mniejsze sesje.",
                    },
                )
            pages[row.normalized_url] = (row.depth, row.final_url is not None, values)
            page_urls[row.id] = row.normalized_url
            error_count += int(row.error is not None)
            if row.fetch_order is not None:
                attempted.append((row.fetch_order, row.normalized_url))
        edges = Counter()
        for row in db.execute(
            select(Link.source_page_id, Link.target_url, Link.kind).where(Link.session_id == run.id)
        ).yield_per(1000):
            edges[(page_urls[row.source_page_id], row.target_url, row.kind)] += 1
        order = [url for _, url in sorted(attempted)]
        orders.append(order)
        pages_by_run.append(pages)
        edges_by_run.append(edges)
        elapsed = (
            (run.finished_at - run.started_at).total_seconds()
            if (run.started_at is not None and run.finished_at is not None)
            else None
        )
        metrics.append(
            RunMetrics(
                session=SessionRead.model_validate(run),
                discovered_pages=len(pages),
                fetched_pages=sum(value[1] for value in pages.values()),
                attempted_pages=len(attempted),
                errored_pages=error_count,
                link_count=sum(edges.values()),
                unique_typed_edges=len(edges),
                reached_depth=max((value[0] for value in pages.values() if value[1]), default=None),
                elapsed_seconds=elapsed if elapsed is not None and elapsed >= 0 else None,
                metadata_present=present,
                retrieval_order=result(order),
            )
        )
    pairs = []
    left = pages_by_run[0]
    for index, right in enumerate(pages_by_run[1:], 1):
        common = set(left) & set(right)
        left_fetched = {url for url, value in left.items() if value[1]}
        right_fetched = {url for url, value in right.items() if value[1]}
        metadata_changes = []
        for url in sorted(left_fetched & right_fetched):
            changed = {
                field: [left[url][2][field], right[url][2][field]]
                for field in CONTENT_FIELDS
                if left[url][2][field].sha256 != right[url][2][field].sha256
            }
            if changed:
                metadata_changes.append(ContentChange(url=url, fields=changed))
        a, b = edges_by_run[0], edges_by_run[index]

        def edge_values(keys):
            return [EdgeKey(source=key[0], target=key[1], kind=key[2]) for key in sorted(keys)]

        config_a = metrics[0].session.config.model_dump(mode="json")
        config_b = metrics[index].session.config.model_dump(mode="json")
        pairs.append(
            PairComparison(
                left_id=ids[0],
                right_id=ids[index],
                config_changes={
                    key: [value, config_b[key]]
                    for key, value in config_a.items()
                    if value != config_b[key]
                },
                discovered=url_sets(set(left), set(right)),
                fetched=url_sets(left_fetched, right_fetched),
                edges=EdgeSets(
                    common=result(edge_values(a.keys() & b.keys())),
                    left_only=result(edge_values(a.keys() - b.keys())),
                    right_only=result(edge_values(b.keys() - a.keys())),
                    multiplicity_changes=result(
                        [
                            EdgeChange(
                                source=key[0],
                                target=key[1],
                                kind=key[2],
                                left_count=a[key],
                                right_count=b[key],
                            )
                            for key in sorted(a.keys() | b.keys())
                            if a[key] != b[key]
                        ]
                    ),
                ),
                metadata_changes=result(metadata_changes),
                depth_changes=result(
                    [
                        DepthChange(url=url, left=left[url][0], right=right[url][0])
                        for url in sorted(common)
                        if left[url][0] != right[url][0]
                    ]
                ),
                retrieval_order_equal=orders[0] == orders[index],
                observations=[
                    f"Wspólne pobrane HTML: {len(left_fetched & right_fetched)}; "
                    f"tylko A: {len(left_fetched - right_fetched)}; "
                    f"tylko B: {len(right_fetched - left_fetched)}.",
                    f"Zmiany metadanych wspólnych HTML: {len(metadata_changes)}.",
                ],
            )
        )
    notes = [
        "BFS/DFS określa kolejność pobierania. Pełne zbiory osiągalnych stron mogą być identyczne.",
        "Czas obejmuje robots, opóźnienia, sieć i analizę; współdzielony limiter i zmiany witryny "
        "nie pozwalają przypisać różnic wyłącznie konfiguracji.",
        "Pomiary nie wskazują uniwersalnie najlepszego wariantu.",
    ]
    if any(
        run.status != SessionStatus.COMPLETED
        or run.stop_reason != "frontier_exhausted"
        or metric.errored_pages
        for run, metric in zip(sessions, metrics, strict=True)
    ):
        notes.append(
            "Wyniki częściowe, z limitem lub błędami. Brak URL nie dowodzi nieosiągalności."
        )
    return ComparisonRead(start_url=sessions[0].start_url, runs=metrics, pairs=pairs, notes=notes)
