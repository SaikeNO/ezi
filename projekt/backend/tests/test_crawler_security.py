import asyncio
import ssl

import httpcore
import httpx
import pytest

from app.crawler.fetcher import Fetcher, OriginLimiter
from app.crawler.network import PinnedBackend, SafeTransport
from app.crawler.robots import parse_robots
from app.crawler.urls import CrawlError, normalize_url, public_ip
from app.schemas import CrawlConfigInput


@pytest.mark.parametrize(
    "value",
    [
        "168.63.129.16",
        "2001:20::1",
        "127.0.0.1",
        "0.0.0.0",
        "10.0.0.1",
        "169.254.169.254",
        "100.100.100.200",
        "192.0.0.8",
        "192.168.1.1",
        "224.0.0.1",
        "198.18.0.1",
        "::1",
        "fd00::1",
        "fe80::1",
        "fec0::1",
        "ff02::1",
        "::ffff:127.0.0.1",
        "64:ff9b::7f00:1",
        "2002:7f00:1::",
        "2606:4700::1%eth0",
    ],
)
def test_nonpublic_and_transition_addresses_blocked(value):
    with pytest.raises(CrawlError):
        public_ip(value)


@pytest.mark.parametrize(
    "source,expected",
    [
        ("HTTPS://EXAMPLE.COM:443/a/../b#x", "https://example.com/b"),
        ("https://example.com/%7euser?q=%41%2f#x", "https://example.com/~user?q=A%2F"),
        ("https://example.com/a/%2e%2e/b", "https://example.com/b"),
        ("https://EXAMPLE.com./", "https://example.com/"),
    ],
)
def test_normalization(source, expected):
    assert normalize_url(source) == expected
    assert normalize_url(expected) == expected


def test_relative_normalization_and_query_order_preserved():
    assert normalize_url("../b#x", "https://example.com/a/c") == "https://example.com/b"
    assert normalize_url("?b=2&a=1", "https://example.com/") == "https://example.com/?b=2&a=1"
    for value in [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://u:p@example.com",
        "//bad_host/",
    ]:
        with pytest.raises(CrawlError):
            normalize_url(value, "https://example.com")


class FakeStream(httpcore.AsyncNetworkStream):
    def __init__(self, peer=("8.8.8.8", 443)):
        self.peer, self.closed, self.writes, self.sni = peer, False, [], None

    def get_extra_info(self, info):
        return self.peer if info == "server_addr" else None

    async def read(self, max_bytes, timeout=None):
        return b""

    async def write(self, buffer, timeout=None):
        self.writes.append(buffer)

    async def aclose(self):
        self.closed = True

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED
        assert ssl_context.check_hostname
        self.sni = server_hostname
        return self


class Connector(httpcore.AsyncNetworkBackend):
    def __init__(self, peer=("8.8.8.8", 443)):
        self.calls = []
        self.stream = FakeStream(peer)

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.calls.append((host, port))
        return self.stream


@pytest.mark.anyio
@pytest.mark.parametrize(
    "records",
    [
        ["8.8.8.8", "127.0.0.1"],
        ["::1"],
        ["169.254.169.254"],
        [],
        ["8.8.8.8"] * 65,
    ],
)
async def test_every_dns_answer_checked_before_connect(records):
    async def resolve(host, port):
        return records

    connector = Connector()
    with pytest.raises(CrawlError):
        await PinnedBackend(resolve, connector).connect_tcp("example.com", 443, 1)
    assert connector.calls == []


@pytest.mark.anyio
async def test_pin_dns_no_second_hostname_lookup_and_preserve_tls_sni():
    calls = []

    async def resolve(host, port):
        calls.append(host)
        return ["8.8.8.8"] if len(calls) == 1 else ["127.0.0.1"]

    connector = Connector()
    backend = PinnedBackend(resolve, connector)
    stream = await backend.connect_tcp("example.com", 443, 1)
    secured = await stream.start_tls(ssl.create_default_context(), "example.com", 1)
    await secured.write(b"GET / HTTP/1.1\r\n\r\n")
    assert connector.calls == [("8.8.8.8", 443)]
    assert connector.stream.sni == "example.com"
    with pytest.raises(CrawlError):
        await backend.connect_tcp("example.com", 443, 1)
    assert len(connector.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("peer", [("127.0.0.1", 443), ("1.1.1.1", 443), ("8.8.8.8", 80), None])
async def test_actual_peer_mismatch_closed_before_any_http_bytes(peer):
    async def resolve(host, port):
        return ["8.8.8.8"]

    connector = Connector(peer)
    with pytest.raises(CrawlError):
        await PinnedBackend(resolve, connector).connect_tcp("example.com", 443, 1)
    assert connector.stream.closed
    assert connector.stream.writes == []


@pytest.mark.anyio
async def test_peer_is_rechecked_before_write():
    async def resolve(host, port):
        return ["8.8.8.8"]

    connector = Connector()
    stream = await PinnedBackend(resolve, connector).connect_tcp("example.com", 443, 1)
    connector.stream.peer = ("127.0.0.1", 443)
    with pytest.raises(CrawlError):
        await stream.write(b"secret")
    assert connector.stream.writes == []


@pytest.mark.anyio
async def test_redirect_dns_to_private_is_blocked_through_real_transport_stack():
    class RedirectStream(FakeStream):
        def __init__(self):
            super().__init__(("8.8.8.8", 80))
            self.sent = False

        async def read(self, max_bytes, timeout=None):
            if self.sent:
                return b""
            self.sent = True
            return (
                b"HTTP/1.1 302 Found\r\nLocation: http://bad.example/\r\n"
                b"Content-Length: 0\r\nConnection: close\r\n\r\n"
            )

    connector = Connector()
    connector.stream = RedirectStream()

    async def resolve(host, port):
        return ["8.8.8.8"] if host == "site.example" else ["127.0.0.1"]

    fetcher = Fetcher(
        CrawlConfigInput(scope="web", follow_external_urls=True, respect_robots=False),
        "http://site.example/",
        OriginLimiter(),
        SafeTransport(PinnedBackend(resolve, connector)),
    )
    try:
        with pytest.raises(CrawlError) as error:
            await fetcher.fetch("http://site.example/")
        assert error.value.code == "unsafe_address"
        assert connector.calls == [("8.8.8.8", 80)]
        assert b"Host: site.example" in b"".join(connector.stream.writes)
    finally:
        await fetcher.aclose()


@pytest.mark.anyio
async def test_request_timeout_is_reported_and_empty_robots_allows():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return response(b"", status=404)
        raise httpx.ReadTimeout("fixture timeout")

    fetcher = Fetcher(
        CrawlConfigInput(request_delay_ms=100),
        "https://example.com/",
        OriginLimiter(),
        httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(CrawlError) as error:
            await fetcher.fetch("https://example.com/")
        assert error.value.code == "request_timeout"
        assert calls == ["/robots.txt", "/"]
    finally:
        await fetcher.aclose()


class BytesStream(httpx.AsyncByteStream):
    def __init__(self, content: bytes):
        self.content = content

    async def __aiter__(self):
        for position in range(0, len(self.content), 200):
            yield self.content[position : position + 200]

    async def aclose(self):
        pass


def response(body=b"<html></html>", status=200, headers=None):
    return httpx.Response(
        status, headers={"Content-Type": "text/html", **(headers or {})}, stream=BytesStream(body)
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "target",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/",
        "file:///etc/passwd",
        "https://user:secret@example.com",
        "https://example.com:8080/",
        "https://other.example/",
    ],
)
async def test_redirect_policy_before_destination_request(target):
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return response(status=302, headers={"Location": target})

    fetcher = Fetcher(
        CrawlConfigInput(respect_robots=False),
        "https://example.com/",
        OriginLimiter(),
        httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(CrawlError):
            await fetcher.fetch("https://example.com/")
        assert requests == ["https://example.com/"]
    finally:
        await fetcher.aclose()


@pytest.mark.anyio
async def test_redirect_loop_bounded_and_size_limits_compressed_rejected():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return response(status=302, headers={"Location": "/"})

    config = CrawlConfigInput(
        max_redirects=2, request_delay_ms=100, respect_robots=False, max_response_bytes=1024
    )
    fetcher = Fetcher(config, "https://example.com/", OriginLimiter(), httpx.MockTransport(handler))
    try:
        with pytest.raises(CrawlError, match="przekierowania"):
            await fetcher.fetch("https://example.com/")
        assert len(calls) == 3
    finally:
        await fetcher.aclose()
    for headers in [{}, {"Content-Length": "5000"}, {"Content-Encoding": "gzip"}]:
        fetcher = Fetcher(
            config,
            "https://example.com/",
            OriginLimiter(),
            httpx.MockTransport(
                lambda request, headers=headers: response(b"x" * 2048, headers=headers)
            ),
        )
        try:
            with pytest.raises(CrawlError):
                await fetcher.fetch("https://example.com/")
        finally:
            await fetcher.aclose()


@pytest.mark.parametrize(
    "path,allowed",
    [
        ("/private/x", False),
        ("/private/public/x", True),
        ("/x.tmp", False),
        ("/x.tmp/next", True),
        ("/any?secret=1", False),
        ("/a[1]", False),
    ],
)
def test_robots_longest_rule_wildcards_end_anchor_literal_characters(path, allowed):
    policy = parse_robots("""User-agent: *
Disallow: /private/
Allow: /private/public/
Disallow: /*.tmp$
Disallow: /*?secret=*
Disallow: /a[1]
""")
    assert policy.allows("https://example.com" + path) == allowed


def test_robots_specific_groups_merge_delay_and_allow_tie():
    policy = parse_robots("""User-agent: *
Disallow: /
User-agent: WebCrawlerStudio
Disallow: /denied
Crawl-delay: 0.5
User-agent: webcrawlerstudio
Allow: /denied
Request-rate: 1/2
""")
    assert policy.allows("https://example.com/denied")
    assert policy.allows("https://example.com/other")
    assert policy.delay == 2
    with pytest.raises(CrawlError):
        parse_robots("User-agent: *\nCrawl-delay: NaN")


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_robots_failure_closed_and_cached(status):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return response(status=status)

    fetcher = Fetcher(
        CrawlConfigInput(), "https://example.com/", OriginLimiter(), httpx.MockTransport(handler)
    )
    try:
        for _ in range(2):
            with pytest.raises(CrawlError):
                await fetcher.fetch("https://example.com/")
        assert calls == ["/robots.txt"]
    finally:
        await fetcher.aclose()


@pytest.mark.anyio
async def test_robots_denial_no_page_request_and_no_env_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1234")
    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert "WebCrawlerStudio" in request.headers["user-agent"]
        assert request.headers["accept-encoding"] == "identity"
        return response(b"User-agent: *\nDisallow: /", headers={"Content-Type": "text/plain"})

    fetcher = Fetcher(
        CrawlConfigInput(), "https://example.com/", OriginLimiter(), httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(CrawlError) as error:
            await fetcher.fetch("https://example.com/")
        assert error.value.code == "robots_denied"
        assert calls == ["/robots.txt"]
    finally:
        await fetcher.aclose()
    transport = SafeTransport()
    assert isinstance(transport.pool._network_backend, PinnedBackend)
    await transport.aclose()


@pytest.mark.anyio
async def test_rate_limiter_shared_origin_spacing_and_cancellable_wait():
    now = 0.0
    waits = []

    async def sleep(seconds):
        nonlocal now
        waits.append(seconds)
        now += seconds

    limiter = OriginLimiter(lambda: now, sleep)
    await limiter.wait("https://example.com/a", 0.5)
    await limiter.wait("https://example.com/b", 2)
    await limiter.wait("https://other.example/", 0.5)
    assert waits == [2]
    limiter = OriginLimiter()
    await limiter.wait("https://example.com/", 60)
    task = asyncio.create_task(limiter.wait("https://example.com/", 60))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.anyio
async def test_origin_slot_covers_dns_body_and_post_completion_delay():
    limiter = OriginLimiter()
    entered, release = asyncio.Event(), asyncio.Event()
    times = []

    async def first():
        async with limiter.slot("https://example.com/", 0.03):
            entered.set()
            await release.wait()
        times.append(asyncio.get_running_loop().time())

    async def second():
        async with limiter.slot("https://example.com/next", 0.03):
            times.append(asyncio.get_running_loop().time())

    task = asyncio.create_task(first())
    await entered.wait()
    other = asyncio.create_task(second())
    await asyncio.sleep(0.01)
    assert times == []
    release.set()
    await asyncio.gather(task, other)
    assert times[1] - times[0] >= 0.025
