"""Persistent crawl engine. Sequential scheduling makes traversal reproducible."""
import asyncio
import csv
import io
import json
import sqlite3
import time
import uuid
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, field_validator

AGENT = "EZILab/1.0"


def now():
    return datetime.now(timezone.utc).isoformat()


def _normalize(url, base=""):
    p = urlsplit(urljoin(base, url.strip()))
    if p.scheme.lower() not in ("http", "https") or not p.hostname or p.username or p.password:
        return None
    try:
        port = p.port
    except ValueError:
        return None
    host = p.hostname.lower().encode("idna").decode()
    if ":" in host:
        host = f"[{host}]"
    if port and port != (443 if p.scheme.lower() == "https" else 80):
        host += f":{port}"
    return urlunsplit((p.scheme.lower(), host, p.path or "/", p.query, ""))


def normalize(url, base=""):
    try:
        return _normalize(url, base)
    except (ValueError, UnicodeError, TypeError):
        return None


def server(url):
    p = urlsplit(url)
    return p.hostname, p.port or (443 if p.scheme == "https" else 80)


class Config(BaseModel):
    url: str
    strategy: Literal["dfs", "bfs"] = "dfs"
    scope: Literal["server", "web"] = "server"
    links: Literal["hyperlinks", "images", "all"] = "hyperlinks"
    depth: int = Field(default=3, ge=0, le=15)
    page_limit: int = Field(default=200, ge=1, le=5000)
    resource_limit: int = Field(default=500, ge=0, le=10000)
    delay: float = Field(default=1, ge=0, le=30)
    timeout: float = Field(default=15, ge=0.1, le=120)

    @field_validator("url")
    @classmethod
    def check_url(cls, value):
        result = normalize(value)
        if not result:
            raise ValueError("Podaj poprawny URL HTTP lub HTTPS, bez danych logowania.")
        return result


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    purpose TEXT NOT NULL, batch_id TEXT, config TEXT NOT NULL,
                    status TEXT NOT NULL, created TEXT NOT NULL, ended TEXT, elapsed REAL DEFAULT 0,
                    requests INTEGER DEFAULT 0, message TEXT DEFAULT '');
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    url TEXT NOT NULL, final_url TEXT, depth INTEGER NOT NULL,
                    kind TEXT NOT NULL, status TEXT NOT NULL, http_status INTEGER,
                    content_type TEXT, bytes INTEGER DEFAULT 0, error TEXT DEFAULT '',
                    UNIQUE(run_id,url));
                CREATE TABLE IF NOT EXISTS metadata (
                    page_id INTEGER PRIMARY KEY REFERENCES pages(id), title TEXT,
                    description TEXT, keywords TEXT, body TEXT);
                CREATE TABLE IF NOT EXISTS links (
                    id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    source TEXT NOT NULL, target TEXT NOT NULL, kind TEXT NOT NULL,
                    disposition TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS page_run ON pages(run_id);
                CREATE INDEX IF NOT EXISTS link_run ON links(run_id);
            """)
            db.execute("UPDATE runs SET status='interrupted', ended=?, message=? WHERE status IN ('queued','running')",
                       (now(), "Przerwano przy ponownym uruchomieniu aplikacji.",))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def execute(self, sql, args=()):
        with self.connect() as db:
            cur = db.execute(sql, args)
            return cur.lastrowid

    def query(self, sql, args=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def get_run(self, run_id):
        rows = self.query("SELECT * FROM runs WHERE id=?", (run_id,))
        if not rows:
            raise KeyError(run_id)
        row = rows[0]
        row["config"] = json.loads(row["config"])
        return row

    def create_run(self, session_id, config, purpose="manual", batch_id=None):
        run_id = uuid.uuid4().hex
        self.execute("INSERT INTO runs(id,session_id,purpose,batch_id,config,status,created) VALUES(?,?,?,?,?,'queued',?)",
                     (run_id, session_id, purpose, batch_id, config.model_dump_json(), now()))
        return run_id

    def records(self, run_id):
        return self.query("""SELECT p.*,m.title,m.description,m.keywords,m.body FROM pages p
            LEFT JOIN metadata m ON p.id=m.page_id WHERE run_id=? ORDER BY p.id""", (run_id,))

    def graph(self, run_id):
        run = self.get_run(run_id)
        nodes = self.records(run_id)
        edges = self.query("SELECT * FROM links WHERE run_id=? ORDER BY id", (run_id,))
        known = {n["url"] for n in nodes}
        depths = {run["config"]["url"]: 0}
        adjacency = {}
        for e in edges:
            if e["kind"] in ("hyperlink", "redirect") and normalize(e["target"]):
                adjacency.setdefault(e["source"], set()).add((e["target"], 0 if e["kind"] == "redirect" else 1))
        queue = deque([run["config"]["url"]])
        while queue:
            source = queue.popleft()
            for target, cost in adjacency.get(source, ()):
                distance = depths[source] + cost
                if distance < depths.get(target, float("inf")):
                    depths[target] = distance
                    if cost:
                        queue.append(target)
                    else:
                        queue.appendleft(target)
        outgoing = {}
        for e in edges:
            outgoing.setdefault(e["source"], []).append(e["target"])
        for n in nodes:
            n["distance"] = depths.get(n["url"])
            n["external"] = server(n["url"]) != server(run["config"]["url"])
            n["outgoing"] = len(outgoing.get(n["url"], []))
            n["unique_targets"] = len(set(outgoing.get(n["url"], [])))
        # Include discovered targets without conflating them with fetched HTML pages.
        for e in edges:
            if e["target"] not in known:
                known.add(e["target"])
                target = normalize(e["target"])
                nodes.append(dict(url=e["target"], kind="page" if e["kind"] == "hyperlink" else "resource",
                                  status=e["disposition"], depth=None, distance=depths.get(e["target"]),
                                  external=bool(target and server(target) != server(run["config"]["url"])),
                                  outgoing=0, unique_targets=0))
        return {"nodes": nodes, "edges": edges}

    def metrics(self, run_id):
        run = self.get_run(run_id)
        graph = self.graph(run_id)
        fetched = [n for n in graph["nodes"] if n["status"] == "ok" and n["kind"] == "page"]
        subpages = [n for n in fetched if n["url"] != run["config"]["url"]]
        depth = max((n["distance"] for n in fetched if n["distance"] is not None), default=0)
        distribution = {}
        for n in fetched:
            key = str(n["distance"]) if n["distance"] is not None else "brak"
            distribution[key] = distribution.get(key, 0) + 1
        return dict(pages=len(fetched), subpages=len(subpages), depth=depth,
                    traversal_depth=max((n["depth"] for n in fetched), default=0),
                    links=len(graph["edges"]), unique_edges=len({(e["source"], e["target"]) for e in graph["edges"]}),
                    resources=sum(n["kind"] == "resource" and n["status"] == "ok" for n in graph["nodes"]),
                    failures=sum(n["status"] == "error" for n in graph["nodes"]),
                    excluded=sum(n["status"] not in ("ok", "error", "pending") for n in graph["nodes"]),
                    distribution=distribution, qualifies=len(subpages) >= 20 and depth >= 3,
                    requests=run["requests"], elapsed=run["elapsed"], status=run["status"],
                    truncated=run["status"] in ("cancelled", "interrupted", "failed") or bool(run["message"]) or any(e["disposition"] in ("depth", "page_limit", "resource_limit") for e in graph["edges"]))


def extract(html, url, mode):
    soup = BeautifulSoup(html, "html.parser")
    base_tag = soup.find("base", href=True)
    base = normalize(base_tag["href"], url) or url if base_tag else url
    links = []
    for tag in soup.find_all(True):
        candidates = []
        if tag.name in ("a", "area") and tag.get("href"):
            candidates.append((tag["href"], "hyperlink"))
        if tag.name in ("frame", "iframe") and tag.get("src"):
            candidates.append((tag["src"], "hyperlink"))
        if mode in ("images", "all") and tag.name in ("img", "input") and tag.get("src"):
            candidates.append((tag["src"], "image"))
        if mode == "all":
            for attr in ("href", "src", "data", "action", "poster", "background", "codebase", "cite", "longdesc", "manifest"):
                value = tag.get(attr)
                if value and (value, "hyperlink") not in candidates and (value, "image") not in candidates:
                    candidates.append((value, "resource"))
            if tag.get("srcset"):
                candidates.extend((v.strip().split()[0], "image") for v in tag["srcset"].split(",") if v.strip())
        for value, kind in candidates:
            try:
                resolved = normalize(value, base) or urljoin(base, value)
            except ValueError:
                resolved = str(value)
            links.append((resolved, kind))
    def meta(name):
        tag = soup.find("meta", attrs={"name": lambda v: v and v.lower() == name})
        return tag.get("content", "") if tag else ""
    metadata = dict(title=soup.title.get_text(" ", strip=True) if soup.title else "",
                    description=meta("description"), keywords=meta("keywords"))
    for tag in soup(["script", "style", "noscript", "template", "head"]):
        tag.decompose()
    metadata["body"] = (soup.body or soup).get_text(" ", strip=True)
    return metadata, links


class Engine:
    def __init__(self, store):
        self.store = store
        self.task = None
        self.cancelled = asyncio.Event()
        self.active_run = None

    @property
    def busy(self):
        return self.task is not None and not self.task.done()

    def start(self, ids):
        if self.busy:
            raise RuntimeError("Inne badanie już trwa.")
        self.cancelled = asyncio.Event()
        self.task = asyncio.create_task(self.batch(ids))

    async def batch(self, ids):
        try:
            for run_id in ids:
                if self.cancelled.is_set():
                    self.store.execute("UPDATE runs SET status='cancelled',ended=? WHERE id=?", (now(), run_id))
                    continue
                self.active_run = run_id
                try:
                    await self.crawl(run_id)
                except Exception as exc:
                    self.store.execute("UPDATE runs SET status='failed',ended=?,message=? WHERE id=?",
                                       (now(), str(exc), run_id))
        finally:
            self.active_run = None

    async def crawl(self, run_id):
        cfg = Config(**self.store.get_run(run_id)["config"])
        started = time.monotonic()
        self.store.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))
        frontier = deque([(cfg.url, 0, "page")])
        scheduled = {cfg.url: 0}
        completed = set()
        parsed_links = {}
        expanded_at = {}
        robots = {}
        requests = 0
        page_count = resource_count = 0
        limits = set()

        def expand(source, depth, found, record=True):
            expanded_at[source] = depth
            pending = []
            for target, link_kind in found:
                normalized = normalize(target)
                disposition = "eligible"
                if not normalized:
                    disposition = "unsupported"
                elif cfg.scope == "server" and server(target) != server(cfg.url):
                    disposition = "scope"
                elif depth >= cfg.depth:
                    disposition = "depth"
                if record:
                    self.store.execute("INSERT INTO links(run_id,source,target,kind,disposition) VALUES(?,?,?,?,?)",
                                       (run_id, source, target, link_kind, disposition))
                elif disposition == "eligible":
                    self.store.execute("UPDATE links SET disposition='eligible' WHERE run_id=? AND source=? AND target=? AND disposition='depth'",
                                       (run_id, source, target))
                if disposition == "eligible" and depth+1 < scheduled.get(target, float("inf")):
                    scheduled[target] = depth+1
                    pending.append((target, depth+1, "page" if link_kind == "hyperlink" else "resource"))
            frontier.extend(pending if cfg.strategy == "bfs" else reversed(pending))

        async with httpx.AsyncClient(timeout=cfg.timeout, headers={"User-Agent": AGENT}) as client:
            async def get(url):
                nonlocal requests
                if self.cancelled.is_set():
                    raise asyncio.CancelledError()
                p = urlsplit(url)
                parser = robots.get(f"{p.scheme}://{p.netloc}")
                delay = cfg.delay
                if parser:
                    delay = max(delay, parser.crawl_delay(AGENT) or 0)
                    rate = parser.request_rate(AGENT)
                    if rate:
                        delay = max(delay, rate.seconds / rate.requests)
                if delay:
                    try:
                        await asyncio.wait_for(self.cancelled.wait(), delay)
                        raise asyncio.CancelledError()
                    except asyncio.TimeoutError:
                        pass
                requests += 1
                self.store.execute("UPDATE runs SET requests=?,elapsed=? WHERE id=?", (requests, time.monotonic()-started, run_id))
                # Bound memory for unexpectedly large resources or HTML documents.
                async with client.stream("GET", url) as response:
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(chunks) + len(chunk) > 5_000_000:
                            raise ValueError("Odpowiedź przekracza limit 5 MB.")
                        chunks.extend(chunk)
                    return httpx.Response(response.status_code, headers=response.headers, content=bytes(chunks), request=response.request)

            async def allowed(url):
                p = urlsplit(url)
                origin = f"{p.scheme}://{p.netloc}"
                if origin not in robots:
                    parser = RobotFileParser()
                    try:
                        response = await get(origin + "/robots.txt")
                        if response.status_code in (401, 403) or response.status_code >= 500 or response.is_redirect:
                            parser.parse(["User-agent: *", "Disallow: /"])
                        elif response.status_code >= 400:
                            parser.parse([])
                        else:
                            parser.parse(response.text.splitlines())
                    except (httpx.HTTPError, ValueError):
                        parser.parse(["User-agent: *", "Disallow: /"])
                    robots[origin] = parser
                return robots[origin].can_fetch(AGENT, url)

            try:
                while frontier and not self.cancelled.is_set():
                    url, depth, kind = frontier.popleft() if cfg.strategy == "bfs" else frontier.pop()
                    if depth > scheduled.get(url, depth):
                        continue
                    if url in completed:
                        # A shorter route may expose children previously beyond the depth limit.
                        # Reuse parsed HTML; never refetch or overwrite first traversal depth.
                        if url in parsed_links and depth < expanded_at[url]:
                            expand(url, depth, parsed_links[url], record=False)
                        continue
                    if kind == "page" and page_count >= cfg.page_limit:
                        status = "page_limit"
                    elif kind == "resource" and resource_count >= cfg.resource_limit:
                        status = "resource_limit"
                    else:
                        status = "pending"
                    page_id = self.store.execute("INSERT OR IGNORE INTO pages(run_id,url,depth,kind,status) VALUES(?,?,?,?,?)",
                                                 (run_id, url, depth, kind, status))
                    if status != "pending":
                        limits.add(status)
                        self.store.execute("UPDATE links SET disposition=? WHERE run_id=? AND target=? AND disposition='eligible'", (status, run_id, url))
                        continue
                    if kind == "page":
                        page_count += 1
                    else:
                        resource_count += 1
                    current = url
                    try:
                        # Validate scope and robots again at every redirect hop.
                        for hop in range(11):
                            if cfg.scope == "server" and server(current) != server(cfg.url):
                                self.store.execute("UPDATE pages SET status='scope',final_url=? WHERE id=?", (current, page_id))
                                break
                            if hop and current in completed:
                                self.store.execute("UPDATE pages SET status='duplicate',final_url=? WHERE id=?", (current, page_id))
                                if current in parsed_links and depth < expanded_at[current]:
                                    expand(current, depth, parsed_links[current], record=False)
                                break
                            if not await allowed(current):
                                self.store.execute("UPDATE pages SET status='robots',final_url=? WHERE id=?", (current, page_id))
                                break
                            response = await get(current)
                            if response.is_redirect:
                                target = normalize(response.headers.get("location", ""), current)
                                if not target or hop == 10:
                                    raise ValueError("Nieprawidłowe przekierowanie lub zbyt wiele przekierowań.")
                                self.store.execute("INSERT INTO links(run_id,source,target,kind,disposition) VALUES(?,?,?,'redirect','redirect')", (run_id, current, target))
                                current = target
                                continue
                            response.raise_for_status()
                            content_type = response.headers.get("content-type", "").lower()
                            is_html = "text/html" in content_type or "application/xhtml+xml" in content_type
                            actual_kind = "page" if is_html else "resource"
                            self.store.execute("UPDATE pages SET final_url=?,kind=?,status='ok',http_status=?,content_type=?,bytes=? WHERE id=?",
                                               (current, actual_kind, response.status_code, content_type, len(response.content), page_id))
                            # Redirect aliases reuse content instead of expanding it twice.
                            if current in completed:
                                self.store.execute("UPDATE pages SET status='duplicate' WHERE id=?", (page_id,))
                                break
                            completed.add(current)
                            if is_html:
                                metadata, found = extract(response.text, current, cfg.links)
                                self.store.execute("INSERT INTO metadata(page_id,title,description,keywords,body) VALUES(?,?,?,?,?)",
                                                   (page_id, metadata["title"], metadata["description"], metadata["keywords"], metadata["body"]))
                                parsed_links[url] = found
                                expand(url, depth, found)
                            break
                        completed.add(url)
                    except (httpx.HTTPError, ValueError) as exc:
                        code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                        self.store.execute("UPDATE pages SET status='error',error=?,http_status=?,final_url=? WHERE id=?", (str(exc) or type(exc).__name__, code, current, page_id))
                        completed.add(url)
            except asyncio.CancelledError:
                self.cancelled.set()
        if self.cancelled.is_set():
            self.store.execute("UPDATE pages SET status='cancelled' WHERE run_id=? AND status='pending'", (run_id,))
        self.store.execute("UPDATE runs SET status=?,ended=?,elapsed=?,requests=?,message=? WHERE id=?",
                           ("cancelled" if self.cancelled.is_set() else "completed", now(), time.monotonic()-started,
                            requests, "Osiągnięte limity: " + ", ".join(sorted(limits)) if limits else "", run_id))


CSV_FIELDS = {"URL": "url", "Keyword": "keywords", "Title": "title", "Description": "description", "Body": "body",
              "Depth": "depth", "Status": "status", "ContentType": "content_type"}


def csv_export(store, run_id, fields=None):
    fields = fields or ["URL", "Keyword"]
    if not fields or any(f not in CSV_FIELDS for f in fields):
        raise ValueError("Nieznane pola CSV.")
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(fields)
    for row in store.records(run_id):
        if row["kind"] == "page" and row["status"] == "ok":
            writer.writerow([row.get(CSV_FIELDS[f]) if row.get(CSV_FIELDS[f]) is not None else "" for f in fields])
    return out.getvalue().encode("utf-8-sig")


def sqlite_export(store, run_id):
    run = store.get_run(run_id)
    db = sqlite3.connect(":memory:")
    db.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE run(id TEXT PRIMARY KEY,config TEXT,purpose TEXT,status TEXT,created TEXT);
        CREATE TABLE pages(id INTEGER PRIMARY KEY,url TEXT UNIQUE,final_url TEXT,depth INTEGER,kind TEXT,status TEXT,http_status INTEGER,bytes INTEGER);
        CREATE TABLE metadata(page_id INTEGER PRIMARY KEY REFERENCES pages(id),title TEXT,description TEXT,keywords TEXT,body TEXT);
        CREATE TABLE links(id INTEGER PRIMARY KEY,source_id INTEGER REFERENCES pages(id),target_url TEXT,kind TEXT,disposition TEXT);
    """)
    db.execute("INSERT INTO run VALUES(?,?,?,?,?)", (run_id, json.dumps(run["config"]), run["purpose"], run["status"], run["created"]))
    ids = {}
    for row in store.records(run_id):
        ids[row["url"]] = row["id"]
        db.execute("INSERT INTO pages VALUES(?,?,?,?,?,?,?,?)", tuple(row[k] for k in ("id", "url", "final_url", "depth", "kind", "status", "http_status", "bytes")))
        if row["title"] is not None:
            db.execute("INSERT INTO metadata VALUES(?,?,?,?,?)", tuple(row[k] for k in ("id", "title", "description", "keywords", "body")))
    for edge in store.query("SELECT * FROM links WHERE run_id=?", (run_id,)):
        db.execute("INSERT INTO links VALUES(?,?,?,?,?)", (edge["id"], ids.get(edge["source"]), edge["target"], edge["kind"], edge["disposition"]))
    db.commit()
    result = db.serialize()
    db.close()
    return result
