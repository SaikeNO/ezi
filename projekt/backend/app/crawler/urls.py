import ipaddress
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from pydantic import HttpUrl, TypeAdapter

from app.models import Scope

URL_ADAPTER = TypeAdapter(HttpUrl)
UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
INTERNAL_SUFFIXES = ("localhost", "local", "internal", "lan", "home", "arpa", "onion")


class CrawlError(Exception):
    def __init__(self, code: str, message: str, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


def public_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise CrawlError("unsafe_address", "Nieprawidłowy adres IP") from error
    if (
        not address.is_global
        or str(address) == "168.63.129.16"
        or address.is_multicast
        or address.is_reserved
        or address.is_loopback
        or address.is_link_local
        or getattr(address, "is_site_local", False)
        or getattr(address, "scope_id", None) is not None
        or (address.version == 4 and address in ipaddress.ip_network("192.0.0.0/24"))
        or (
            address.version == 6
            and (
                address.ipv4_mapped is not None
                or address.sixtofour is not None
                or address.teredo is not None
                or address in ipaddress.ip_network("2001::/23")
                or address in ipaddress.ip_network("64:ff9b::/96")
                or address in ipaddress.ip_network("64:ff9b:1::/48")
            )
        )
    ):
        raise CrawlError("unsafe_address", "Zablokowano niepubliczny lub zastrzeżony adres IP")
    return address


def percent_normalize(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        char = chr(int(match[0][1:], 16))
        return char if char in UNRESERVED else match[0].upper()

    return re.sub(r"%[0-9a-fA-F]{2}", replace, value)


def normalize_url(value: str, base: str | None = None) -> str:
    """Canonical HTTP URL; discovered unsafe destinations can be stored, never fetched."""
    if (
        not value
        or len(value) > 2048
        or "\\" in value
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise CrawlError("invalid_url", "Nieprawidłowy adres URL")
    try:
        absolute = urljoin(base, value) if base else value
        parts = urlsplit(absolute)
        if parts.username is not None or parts.password is not None:
            raise ValueError("credentials")
        canonical = str(URL_ADAPTER.validate_python(percent_normalize(absolute)))
        parts = urlsplit(canonical)
        host = (parts.hostname or "").rstrip(".").lower()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if (
                not host
                or len(host) > 253
                or not all(
                    re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                    for label in host.split(".")
                )
            ):
                raise ValueError("host") from None
        authority = f"[{host}]" if ":" in host else host
        default_port = 443 if parts.scheme == "https" else 80
        if parts.port is not None and parts.port != default_port:
            authority += f":{parts.port}"
        result = urlunsplit((parts.scheme, authority, parts.path or "/", parts.query, ""))
        if len(result) > 2048:
            raise ValueError("length")
        return result
    except (ValueError, TypeError) as error:
        raise CrawlError("invalid_url", "Nieprawidłowy adres URL HTTP/HTTPS") from error


def validate_destination(value: str) -> str:
    url = normalize_url(value)
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port not in {None, 80, 443} or parts.scheme not in {"http", "https"}:
        raise CrawlError("unsafe_url", "Dozwolone są wyłącznie HTTP/HTTPS na portach 80/443")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or any(
            host == suffix or host.endswith("." + suffix) for suffix in INTERNAL_SUFFIXES
        ):
            raise CrawlError("unsafe_host", "Zablokowano wewnętrzną nazwę hosta") from None
    else:
        public_ip(host)
    return url


def origin(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def same_host(first: str, second: str) -> bool:
    return urlsplit(first).hostname == urlsplit(second).hostname


def in_scope(url: str, start: str, scope: Scope, follow_external: bool) -> bool:
    return same_host(url, start) or (scope == Scope.WEB and follow_external)
