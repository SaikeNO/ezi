"""Controlled TCP website. Test-only backend mapping is never shipped in Docker."""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpcore

from app.crawler.network import SafeTransport

ROOT = "http://site.example"
GRAPH = {
    "/": '<a href="/a#x">A</a><a href="/a#y">A again</a><a href="/b">B</a>'
    '<img src="/image.png"><link rel="stylesheet" href="/style.css">'
    '<script src="/app.js"></script>',
    "/a": '<a href="/a1">A1</a><a href="/a2">A2</a><a href="/">cycle</a>',
    "/b": '<a href="/b1">B1</a>',
    "/a1": '<a href="/a11">A11</a>',
    "/a2": "A2",
    "/a11": "A11",
    "/b1": "B1",
}


class LocalFixtureBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, port: int):
        self.port = port
        self.backend = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        assert host in {"site.example", "other.example"}, host
        assert port == 80
        return await self.backend.connect_tcp("127.0.0.1", self.port, timeout)


class Website:
    def __init__(self, pages=None, robots="User-agent: *\nDisallow:"):
        self.pages = GRAPH if pages is None else pages
        self.robots = robots
        self.requests: list[tuple[str, float, str]] = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.port = 0

    def transport(self):
        return SafeTransport(LocalFixtureBackend(self.port))


@contextmanager
def website(pages=None, robots="User-agent: *\nDisallow:") -> Iterator[Website]:
    site = Website(pages, robots)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            site.requests.append((self.path, time.monotonic(), self.headers.get("Host", "")))
            if self.path == "/slow":
                site.entered.set()
                site.release.wait(15)
            value = (
                site.robots
                if self.path == "/robots.txt"
                else site.pages.get(self.path, (404, {}, "missing"))
            )
            status, headers, body = value if isinstance(value, tuple) else (200, {}, value)
            content = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header(
                "Content-Type",
                headers.get(
                    "Content-Type", "text/plain" if self.path == "/robots.txt" else "text/html"
                ),
            )
            for name, item in headers.items():
                if name.lower() != "content-type":
                    self.send_header(name, item)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    site.port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield site
    finally:
        site.release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)
