import asyncio
import socket
import ssl
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from typing import Any

import httpcore
import httpx

from app.crawler.urls import CrawlError, public_ip

Resolver = Callable[[str, int], Awaitable[list[str]]]


async def resolve_addresses(host: str, port: int) -> list[str]:
    records = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )
    if any(len(record[4]) > 3 and record[4][3] != 0 for record in records):
        raise CrawlError("unsafe_dns", "Zablokowano adres DNS z zakresem interfejsu")
    return list(dict.fromkeys(record[4][0] for record in records))


class VerifiedStream(httpcore.AsyncNetworkStream):
    def __init__(self, stream: httpcore.AsyncNetworkStream, expected: str, port: int):
        self.stream, self.expected, self.port = stream, expected, port

    def verify(self) -> None:
        peer = self.stream.get_extra_info("server_addr")
        if not isinstance(peer, tuple) or len(peer) < 2:
            raise CrawlError("unverified_peer", "Brak potwierdzenia adresu połączenia")
        address = public_ip(peer[0])
        if str(address) != self.expected or peer[1] != self.port:
            raise CrawlError("peer_mismatch", "Adres połączenia nie odpowiada sprawdzonemu DNS")

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        self.verify()
        return await self.stream.read(max_bytes, timeout)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.verify()
        await self.stream.write(buffer, timeout)

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            self.verify()
            secured = await self.stream.start_tls(ssl_context, server_hostname, timeout)
            result = VerifiedStream(secured, self.expected, self.port)
            result.verify()
            return result
        except BaseException:
            await self.aclose()
            raise

    def get_extra_info(self, info: str) -> Any:
        return self.stream.get_extra_info(info)

    async def aclose(self) -> None:
        await self.stream.aclose()


class PinnedBackend(httpcore.AsyncNetworkBackend):
    """Resolve all addresses, reject any unsafe answer, connect only to a checked IP."""

    def __init__(
        self,
        resolver: Resolver = resolve_addresses,
        connector: httpcore.AsyncNetworkBackend | None = None,
    ):
        self.resolver = resolver
        self.connector = connector or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if port not in {80, 443}:
            raise CrawlError("unsafe_port", "Zablokowano port połączenia")
        async with asyncio.timeout(timeout):
            try:
                records = await self.resolver(host, port)
            except OSError as error:
                raise CrawlError("dns_failed", "Nie udało się rozwiązać nazwy DNS") from error
            if not records or len(records) > 64:
                raise CrawlError("unsafe_dns", "Brak poprawnego, ograniczonego zestawu adresów DNS")
            addresses = list(dict.fromkeys(str(public_ip(record)) for record in records))
            last_error: Exception | None = None
            for address in addresses:
                try:
                    stream = await self.connector.connect_tcp(
                        address, port, timeout, local_address, socket_options
                    )
                except (OSError, httpcore.NetworkError, httpcore.TimeoutException) as error:
                    last_error = error
                    continue
                try:
                    checked = VerifiedStream(stream, address, port)
                    checked.verify()
                    return checked
                except BaseException:
                    await stream.aclose()
                    raise
            raise CrawlError(
                "connect_failed", "Nie udało się nawiązać bezpiecznego połączenia"
            ) from last_error

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class CoreStream(httpx.AsyncByteStream):
    def __init__(self, stream: Any):
        self.stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self.stream:
                yield chunk
        except (httpcore.NetworkError, httpcore.TimeoutException, httpcore.ProtocolError) as error:
            raise httpx.TransportError(type(error).__name__) from error

    async def aclose(self) -> None:
        await self.stream.aclose()


class SafeTransport(httpx.AsyncBaseTransport):
    """Public HTTPX/httpcore interfaces; no proxies, cookies from browsers, or DNS relookup."""

    def __init__(self, backend: httpcore.AsyncNetworkBackend | None = None):
        self.pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=backend or PinnedBackend(),
            max_connections=8,
            max_keepalive_connections=0,
            retries=0,
            http1=True,
            http2=False,
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        try:
            response = await self.pool.handle_async_request(core_request)
        except (httpcore.NetworkError, httpcore.TimeoutException, httpcore.ProtocolError) as error:
            raise httpx.TransportError(type(error).__name__) from error
        return httpx.Response(
            response.status,
            headers=response.headers,
            stream=CoreStream(response.stream),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self.pool.aclose()
