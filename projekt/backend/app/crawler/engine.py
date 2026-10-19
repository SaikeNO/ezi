import asyncio
import logging
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from app.crawler.discovery import Reference, extract
from app.crawler.events import record
from app.crawler.fetcher import Fetcher
from app.crawler.urls import CrawlError, in_scope, normalize_url, same_host
from app.models import CrawlSession, Link, LinkKind, Page, SessionStatus, Strategy, new_id, utc_now
from app.schemas import CrawlConfigInput

logger = logging.getLogger(__name__)
MAX_DISCOVERED_PAGES = 50000
MAX_SESSION_LINKS = 200000


@dataclass
class Node:
    id: str
    url: str
    depth: int
    order: int
    attempted: bool = False
    expanded_depth: int | None = None
    references: list[Reference] = field(default_factory=list)


class CrawlEngine:
    def __init__(
        self,
        engine: Engine,
        session_id: str,
        config: CrawlConfigInput,
        start_url: str,
        fetcher: Fetcher,
        cancel_reason: Callable[[], str] | None = None,
    ):
        self.engine, self.session_id, self.config = engine, session_id, config
        self.start_url, self.fetcher = normalize_url(start_url), fetcher
        self.cancel_reason = cancel_reason or (lambda: "user_cancelled")
        self.nodes: dict[str, Node] = {}
        self.frontier: deque[str] = deque()
        self.queued: set[str] = set()
        self.attempts = 0
        self.links = 0
        self.stop_reason = "frontier_exhausted"

    def eligible(self, node: Node) -> bool:
        return (
            node.depth <= self.config.max_depth
            and (not self.config.process_one_page or node.url == self.start_url)
            and in_scope(
                node.url, self.start_url, self.config.scope, self.config.follow_external_urls
            )
        )

    def enqueue(self, nodes: list[Node]) -> None:
        ordered = reversed(nodes) if self.config.strategy == Strategy.DFS else nodes
        for node in ordered:
            if (
                self.eligible(node)
                and node.url not in self.queued
                and (
                    not node.attempted
                    or (node.expanded_depth is not None and node.depth < node.expanded_depth)
                )
            ):
                self.frontier.append(node.url)
                self.queued.add(node.url)

    def seed(self) -> None:
        node = Node(new_id(), self.start_url, 0, 0)
        self.nodes[node.url] = node
        with Session(self.engine) as db:
            crawl = db.get(CrawlSession, self.session_id)
            db.add(
                Page(
                    id=node.id,
                    session_id=self.session_id,
                    normalized_url=node.url,
                    original_url=crawl.start_url,
                    depth=0,
                    discovery_order=0,
                )
            )
            crawl.discovered_count = 1
            record(db, crawl, "page_discovered", page_id=node.id, url=node.url, depth=0)
            db.commit()
        self.enqueue([node])

    def begin_attempt(self, node: Node) -> None:
        node.attempted = True
        with Session(self.engine) as db:
            page = db.get(Page, node.id)
            page.fetch_order = self.attempts
            db.execute(
                update(Link)
                .where(
                    Link.session_id == self.session_id,
                    Link.target_url == node.url,
                    Link.kind == LinkKind.HYPERLINK,
                )
                .values(is_followed=True)
            )
            db.commit()
        self.attempts += 1

    def expand(self, db: Session, crawl: CrawlSession, node: Node, save_links: bool) -> list[Node]:
        candidates: list[Node] = []
        links: list[Link] = []
        for reference in node.references:
            target = None
            if reference.kind == LinkKind.HYPERLINK:
                target = self.nodes.get(reference.url)
                depth = node.depth + 1
                if target is None:
                    if len(self.nodes) >= MAX_DISCOVERED_PAGES:
                        raise CrawlError("discovery_limit", "Osiągnięto limit odkrytych stron")
                    target = Node(new_id(), reference.url, depth, len(self.nodes))
                    self.nodes[target.url] = target
                    db.add(
                        Page(
                            id=target.id,
                            session_id=self.session_id,
                            normalized_url=target.url,
                            original_url=reference.url,
                            depth=depth,
                            discovery_order=target.order,
                        )
                    )
                    crawl.discovered_count += 1
                    record(
                        db, crawl, "page_discovered", page_id=target.id, url=target.url, depth=depth
                    )
                elif depth < target.depth:
                    target.depth = depth
                    db.execute(update(Page).where(Page.id == target.id).values(depth=depth))
                candidates.append(target)
            if save_links:
                if self.links >= MAX_SESSION_LINKS:
                    raise CrawlError("link_limit", "Osiągnięto limit odnośników sesji")
                links.append(
                    Link(
                        session_id=self.session_id,
                        source_page_id=node.id,
                        target_url=reference.url,
                        target_page_id=target.id if target else None,
                        kind=reference.kind,
                        is_external=not same_host(reference.url, self.start_url),
                        is_followed=bool(target and target.attempted),
                    )
                )
                self.links += 1
                crawl.link_count += 1
        db.flush()  # Source/target pages exist before inserting links with composite FKs.
        db.add_all(links)
        node.expanded_depth = node.depth
        return candidates

    async def visit(self, node: Node) -> None:
        if node.attempted:
            with Session(self.engine) as db:
                crawl = db.get(CrawlSession, self.session_id)
                candidates = self.expand(db, crawl, node, save_links=False)
                db.commit()
            self.enqueue(candidates)
            return
        self.begin_attempt(node)
        try:
            document = await self.fetcher.fetch(node.url)
            with Session(self.engine) as db:
                crawl, page = db.get(CrawlSession, self.session_id), db.get(Page, node.id)
                page.http_status, page.final_url = document.status, document.url
                page.content_type, page.encoding = document.content_type, document.encoding
                crawl.fetched_count += 1
                record(
                    db,
                    crawl,
                    "page_fetched",
                    page_id=node.id,
                    url=node.url,
                    final_url=document.url,
                    depth=node.depth,
                )
                db.commit()
            parse_cancelled = threading.Event()
            try:
                extracted = await asyncio.to_thread(
                    extract,
                    document.body,
                    document.url,
                    self.config.link_types,
                    document.encoding,
                    cancelled=parse_cancelled,
                    time_budget=self.config.timeout_seconds,
                )
            finally:
                parse_cancelled.set()
            node.references = extracted.references
            with Session(self.engine) as db:
                crawl, page = db.get(CrawlSession, self.session_id), db.get(Page, node.id)
                page.title, page.description = extracted.title, extracted.description
                page.keywords, page.body = extracted.keywords, extracted.body
                page.encoding = extracted.encoding
                db.commit()  # Keep metadata even if discovery hits a session budget.
                candidates = self.expand(db, crawl, node, save_links=True)
                db.flush()
                record(db, crawl, "progress")
                db.commit()
            self.enqueue(candidates)
        except CrawlError as error:
            with Session(self.engine) as db:
                crawl, page = db.get(CrawlSession, self.session_id), db.get(Page, node.id)
                page.error = f"{error.code}: {error}"
                if error.status is not None:
                    page.http_status = error.status
                crawl.error_count += 1
                record(
                    db,
                    crawl,
                    "page_failed",
                    page_id=node.id,
                    url=node.url,
                    error_code=error.code,
                    message=str(error),
                )
                record(db, crawl, "progress")
                db.commit()
            if error.code in {"link_limit", "discovery_limit", "origin_limit"}:
                self.stop_reason = error.code
                self.frontier.clear()

    def finish(self, status: SessionStatus, reason: str, message: str | None = None) -> None:
        with Session(self.engine) as db:
            crawl = db.get(CrawlSession, self.session_id)
            if crawl is None or crawl.status != SessionStatus.RUNNING:
                return
            crawl.status, crawl.stop_reason = status, reason
            crawl.finished_at, crawl.error = utc_now(), message
            kind = "failure" if status == SessionStatus.FAILED else status.value
            record(db, crawl, kind)
            db.commit()

    async def run(self) -> None:
        try:
            async with asyncio.timeout(self.config.max_duration_seconds):
                self.seed()
                while self.frontier:
                    await asyncio.sleep(0)  # Cancellation boundary before every selection.
                    url = (
                        self.frontier.pop()
                        if self.config.strategy == Strategy.DFS
                        else self.frontier.popleft()
                    )
                    self.queued.remove(url)
                    node = self.nodes[url]
                    if not self.eligible(node):
                        continue
                    if not node.attempted and self.attempts >= self.config.max_pages:
                        self.stop_reason = "page_limit"
                        break
                    await self.visit(node)
                with Session(self.engine) as db:
                    crawl = db.get(CrawlSession, self.session_id)
                    failed = crawl.fetched_count == 0 and crawl.error_count > 0
                self.finish(
                    SessionStatus.FAILED if failed else SessionStatus.COMPLETED,
                    "start_failed" if failed else self.stop_reason,
                    "Nie udało się pobrać żadnej strony HTML" if failed else None,
                )
        except asyncio.CancelledError:
            self.finish(SessionStatus.CANCELLED, self.cancel_reason())
            raise
        except TimeoutError:
            self.finish(SessionStatus.COMPLETED, "time_limit")
        except Exception:
            logger.exception("Crawler session failed: %s", self.session_id)
            self.finish(SessionStatus.FAILED, "internal_error", "Wewnętrzny błąd crawlera")
        finally:
            await self.fetcher.aclose()
