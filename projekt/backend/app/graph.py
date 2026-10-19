"""Read-only graph projections from one SQLite snapshot, never crawler counters."""

from collections import defaultdict
from hashlib import sha256
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crawler.urls import same_host
from app.models import CrawlSession, Link, LinkKind, Page, SessionStatus

MAX_GRAPH_NODES = 5000
MAX_GRAPH_EDGES = 20000


class Degree(BaseModel):
    in_degree: int = 0
    out_degree: int = 0
    unique_in_degree: int = 0
    unique_out_degree: int = 0


class GraphNode(Degree):
    id: str
    page_id: UUID | None
    url: str
    title: str | None
    depth: int
    fetched: bool
    is_external: bool
    http_status: int | None
    error: str | None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    target_url: str
    kind: LinkKind
    is_external: bool
    is_followed: bool


class GraphSummary(BaseModel):
    node_count: int
    page_count: int
    resource_target_count: int
    fetched_pages: int
    errored_pages: int
    reached_depth: int | None
    discovered_depth: int | None
    link_count: int
    unique_relations: int
    internal_links: int
    external_links: int
    root_links: int
    root_unique_targets: int
    subpage_links: int
    subpage_unique_targets: int


class DepthStats(BaseModel):
    depth: int
    pages: int
    fetched_pages: int
    outgoing_links: int


class PageStats(Degree):
    page_id: UUID
    url: str
    depth: int
    fetched: bool


class GraphStats(BaseModel):
    session_id: UUID
    status: SessionStatus
    summary: GraphSummary
    per_depth: list[DepthStats]
    per_page: list[PageStats]


class GraphRead(BaseModel):
    session_id: UUID
    status: SessionStatus
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    summary: GraphSummary
    per_depth: list[DepthStats]


def graph_too_large() -> None:
    raise HTTPException(
        413,
        detail={
            "code": "graph_too_large",
            "message": "Limit grafu: 5000 węzłów, 20000 linków. Statystyki dostępne.",
        },
    )


def projection(
    db: Session,
    session_id: UUID,
    *,
    graph_limits: tuple[int, int] | None = None,
    include_edges: bool = True,
) -> tuple[GraphRead, GraphStats]:
    # sqlite3 legacy transaction mode does not BEGIN for SELECT on Python 3.12.
    # Explicit transaction keeps pages, links and status consistent during crawling.
    db.connection().exec_driver_sql("BEGIN")
    crawl = db.get(CrawlSession, str(session_id))
    if crawl is None:
        raise HTTPException(
            404, detail={"code": "session_not_found", "message": "Nie znaleziono sesji"}
        )
    if graph_limits is not None:
        page_count = (
            db.scalar(
                select(func.count()).select_from(Page).where(Page.session_id == str(session_id))
            )
            or 0
        )
        link_count = (
            db.scalar(
                select(func.count()).select_from(Link).where(Link.session_id == str(session_id))
            )
            or 0
        )
        if page_count > graph_limits[0] or link_count > graph_limits[1]:
            graph_too_large()
    pages = db.execute(
        select(
            Page.id,
            Page.normalized_url,
            func.substr(Page.title, 1, 500).label("title"),
            Page.depth,
            Page.final_url,
            Page.http_status,
            Page.error,
        )
        .where(Page.session_id == str(session_id))
        .order_by(Page.discovery_order, Page.id)
    ).all()
    links = db.execute(
        select(
            Link.id,
            Link.source_page_id,
            Link.target_url,
            Link.kind,
            Link.is_external,
            Link.is_followed,
        )
        .where(Link.session_id == str(session_id))
        .order_by(Link.id)
    ).yield_per(1000)
    nodes: dict[str, GraphNode] = {}
    by_url: dict[str, str] = {}
    for page in pages:
        node_id = "page:" + page.id
        by_url[page.normalized_url] = node_id
        nodes[node_id] = GraphNode(
            id=node_id,
            page_id=page.id,
            url=page.normalized_url,
            title=page.title[:500] if page.title is not None else None,
            depth=page.depth,
            fetched=page.final_url is not None,
            is_external=not same_host(page.normalized_url, crawl.start_url),
            http_status=page.http_status,
            error=page.error,
        )
    edges: list[GraphEdge] = []
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    root_targets: set[str] = set()
    sub_targets: set[str] = set()
    root_links = external_links = link_count = 0
    for link in links:
        link_count += 1
        source = nodes["page:" + link.source_page_id]
        if link.target_url not in by_url:
            node_id = "target:" + sha256(link.target_url.encode("utf-8")).hexdigest()
            by_url[link.target_url] = node_id
            nodes[node_id] = GraphNode(
                id=node_id,
                page_id=None,
                url=link.target_url,
                title=None,
                depth=source.depth + 1,
                fetched=False,
                is_external=not same_host(link.target_url, crawl.start_url),
                http_status=None,
                error=None,
            )
            if graph_limits is not None and len(nodes) > graph_limits[0]:
                graph_too_large()
        target = nodes[by_url[link.target_url]]
        if target.page_id is None:
            target.depth = min(target.depth, source.depth + 1)
        source.out_degree += 1
        target.in_degree += 1
        outgoing[source.id].add(target.id)
        incoming[target.id].add(source.id)
        external_links += int(link.is_external)
        if source.depth == 0:
            root_links += 1
            root_targets.add(target.id)
        else:
            sub_targets.add(target.id)
        if include_edges:
            edges.append(
                GraphEdge(
                    id="link:" + link.id,
                    source=source.id,
                    target=target.id,
                    target_url=link.target_url,
                    kind=link.kind,
                    is_external=link.is_external,
                    is_followed=link.is_followed,
                )
            )
    depths: dict[int, DepthStats] = {}
    per_page: list[PageStats] = []
    for node in nodes.values():
        node.unique_in_degree = len(incoming[node.id])
        node.unique_out_degree = len(outgoing[node.id])
        if node.page_id is not None:
            level = depths.setdefault(
                node.depth,
                DepthStats(
                    depth=node.depth,
                    pages=0,
                    fetched_pages=0,
                    outgoing_links=0,
                ),
            )
            level.pages += 1
            level.fetched_pages += int(node.fetched)
            level.outgoing_links += node.out_degree
            per_page.append(
                PageStats(
                    page_id=node.page_id,
                    url=node.url,
                    depth=node.depth,
                    fetched=node.fetched,
                    **{field: getattr(node, field) for field in Degree.model_fields},
                )
            )
    summary = GraphSummary(
        node_count=len(nodes),
        page_count=len(pages),
        resource_target_count=len(nodes) - len(pages),
        fetched_pages=sum(node.fetched for node in nodes.values()),
        errored_pages=sum(node.error is not None for node in nodes.values()),
        reached_depth=max((node.depth for node in nodes.values() if node.fetched), default=None),
        discovered_depth=max(depths, default=None),
        link_count=link_count,
        unique_relations=sum(len(values) for values in outgoing.values()),
        internal_links=link_count - external_links,
        external_links=external_links,
        root_links=root_links,
        root_unique_targets=len(root_targets),
        subpage_links=link_count - root_links,
        subpage_unique_targets=len(sub_targets),
    )
    per_depth = [depths[depth] for depth in sorted(depths)]
    return (
        GraphRead(
            session_id=session_id,
            status=crawl.status,
            nodes=list(nodes.values()),
            edges=edges,
            summary=summary,
            per_depth=per_depth,
        ),
        GraphStats(
            session_id=session_id,
            status=crawl.status,
            summary=summary,
            per_depth=per_depth,
            per_page=per_page,
        ),
    )
