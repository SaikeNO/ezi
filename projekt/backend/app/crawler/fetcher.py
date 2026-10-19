import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx

from app.crawler.network import SafeTransport
from app.crawler.robots import USER_AGENT, Policy, parse_robots
from app.crawler.urls import CrawlError, in_scope, normalize_url, origin, validate_destination
from app.schemas import CrawlConfigInput


@dataclass
class OriginState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_start: float | None = None
    delay: float = 0


class OriginLimiter:
    """Shared across sessions. Completion-to-next-start spacing includes robots/redirects."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.clock, self.sleep = clock, sleep
        self.origins: OrderedDict[str, OriginState] = OrderedDict()
        self.semaphore = asyncio.Semaphore(8)

    @asynccontextmanager
    async def slot(self, url: str, delay: float):
        key = origin(url)
        if key not in self.origins:
            if len(self.origins) >= 10000:
                for old, state in list(self.origins.items()):
                    if not state.lock.locked() and (
                        state.last_start is None or self.clock() >= state.last_start + state.delay
                    ):
                        del self.origins[old]
                        break
                else:
                    raise CrawlError("origin_limit", "Osiągnięto limit aktywnych hostów")
            self.origins[key] = OriginState()
        state = self.origins[key]
        async with state.lock:
            if state.last_start is not None:
                remaining = state.last_start + max(delay, state.delay) - self.clock()
                if remaining > 0:
                    await self.sleep(remaining)
            state.last_start, state.delay = self.clock(), delay
            self.origins.move_to_end(key)
            try:
                yield
            finally:
                state.last_start = self.clock()

    async def wait(self, url: str, delay: float) -> None:
        async with self.slot(url, delay):
            pass


@dataclass(frozen=True)
class Document:
    url: str
    status: int
    content_type: str
    encoding: str
    body: bytes


class Fetcher:
    def __init__(
        self,
        config: CrawlConfigInput,
        start_url: str,
        limiter: OriginLimiter,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.config, self.start_url, self.limiter = config, start_url, limiter
        self.client = httpx.AsyncClient(
            transport=transport or SafeTransport(),
            trust_env=False,
            follow_redirects=False,
            timeout=config.timeout_seconds,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Encoding": "identity",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.5",
            },
        )
        self.policies: dict[str, Policy] = {}

    async def aclose(self) -> None:
        await self.client.aclose()

    def check(self, url: str) -> str:
        url = validate_destination(url)
        if not in_scope(url, self.start_url, self.config.scope, self.config.follow_external_urls):
            raise CrawlError("out_of_scope", "Przekierowanie poza dozwolony zakres")
        return url

    async def robots(self, url: str) -> Policy:
        key = origin(url)
        if key not in self.policies:
            self.policies[key] = Policy(denied=True)  # Fail closed, including later attempts.
            try:
                document = await self.request(
                    key + "/robots.txt",
                    robots=True,
                    maximum=min(524288, self.config.max_response_bytes),
                )
                if document.status in {404, 410}:
                    self.policies[key] = Policy()
                elif document.status == 200 and document.content_type in {
                    "text/plain",
                    "application/octet-stream",
                    "",
                }:
                    self.policies[key] = parse_robots(
                        document.body.decode("utf-8-sig", errors="strict")
                    )
                else:
                    raise CrawlError(
                        "robots_unavailable", "robots.txt nie pozwala na bezpieczny odczyt"
                    )
            except (CrawlError, UnicodeError) as error:
                raise CrawlError(
                    "robots_unavailable", "Nie udało się bezpiecznie odczytać robots.txt"
                ) from error
        return self.policies[key]

    async def fetch(self, url: str) -> Document:
        return await self.request(url)

    async def request(self, url: str, robots: bool = False, maximum: int | None = None) -> Document:
        current = self.check(url)
        for hop in range(self.config.max_redirects + 1):
            delay = self.config.request_delay_ms / 1000
            if not robots and self.config.respect_robots:
                policy = await self.robots(current)
                if not policy.allows(current):
                    raise CrawlError("robots_denied", "Adres zablokowany przez robots.txt")
                delay = max(delay, policy.delay)
            async with self.limiter.semaphore, self.limiter.slot(current, delay):
                try:
                    async with asyncio.timeout(self.config.timeout_seconds):
                        # Never carry remote cookies to another request or origin.
                        self.client.cookies.clear()
                        async with self.client.stream("GET", current) as response:
                            if response.status_code in {301, 302, 303, 307, 308}:
                                location = response.headers.get("location")
                                if not location or hop == self.config.max_redirects:
                                    raise CrawlError(
                                        "redirect_limit",
                                        "Nieprawidłowe lub zbyt liczne przekierowania",
                                        response.status_code,
                                    )
                                target = self.check(normalize_url(location, current))
                                if robots and origin(target) != origin(url):
                                    raise CrawlError(
                                        "robots_redirect", "robots.txt przekierowuje poza origin"
                                    )
                                current = target
                                continue
                            content_type = (
                                response.headers.get("content-type", "")
                                .split(";", 1)[0]
                                .strip()
                                .lower()
                            )
                            if not robots and (
                                not 200 <= response.status_code < 300
                                or content_type not in {"text/html", "application/xhtml+xml"}
                            ):
                                code = (
                                    "http_error"
                                    if not 200 <= response.status_code < 300
                                    else "non_html"
                                )
                                raise CrawlError(
                                    code,
                                    "Odpowiedź HTTP nie jest poprawną stroną HTML",
                                    response.status_code,
                                )
                            if (
                                response.headers.get("content-encoding", "identity").lower()
                                != "identity"
                            ):
                                raise CrawlError(
                                    "compressed_response",
                                    "Serwer zignorował wymóg odpowiedzi bez kompresji",
                                    response.status_code,
                                )
                            cap = maximum if maximum is not None else self.config.max_response_bytes
                            length = response.headers.get("content-length")
                            if length:
                                try:
                                    if int(length) < 0 or int(length) > cap:
                                        raise CrawlError(
                                            "response_size",
                                            "Odpowiedź przekracza limit rozmiaru",
                                            response.status_code,
                                        )
                                except ValueError as error:
                                    raise CrawlError(
                                        "invalid_length", "Nieprawidłowy rozmiar odpowiedzi"
                                    ) from error
                            content = bytearray()
                            async for chunk in response.aiter_raw(chunk_size=16384):
                                if len(content) + len(chunk) > cap:
                                    raise CrawlError(
                                        "response_size",
                                        "Odpowiedź przekracza limit rozmiaru",
                                        response.status_code,
                                    )
                                content.extend(chunk)
                            return Document(
                                current,
                                response.status_code,
                                content_type,
                                response.encoding or "utf-8",
                                bytes(content),
                            )
                except TimeoutError as error:
                    raise CrawlError("request_timeout", "Przekroczono czas żądania") from error
                except httpx.TimeoutException as error:
                    raise CrawlError("request_timeout", "Przekroczono czas żądania") from error
                except httpx.HTTPError as error:
                    raise CrawlError("request_failed", "Błąd bezpiecznego żądania HTTP") from error
        raise CrawlError("redirect_limit", "Przekroczono limit przekierowań")
