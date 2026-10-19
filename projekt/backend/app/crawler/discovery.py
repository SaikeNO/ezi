import threading
import time
from dataclasses import dataclass
from html.parser import HTMLParser

from app.crawler.urls import CrawlError, normalize_url
from app.models import LinkKind, LinkSelection

MAX_LINKS_PER_PAGE = 5000
MAX_TAGS_PER_PAGE = 100000
MAX_UNFINISHED_TAG = 65536


@dataclass(frozen=True)
class Reference:
    url: str
    kind: LinkKind


class DiscoveryParser(HTMLParser):
    """Navigation only. Title/meta/body extraction is deliberately a later phase."""

    def __init__(self, mode: LinkSelection):
        super().__init__(convert_charrefs=True)
        self.mode = mode
        self.references: list[tuple[str, LinkKind]] = []
        self.base_href: str | None = None
        self.tags = 0
        self.consumed = 0

    def updatepos(self, start: int, end: int) -> int:
        result = super().updatepos(start, end)
        self.consumed += end - start
        return result

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags += 1
        if self.tags > MAX_TAGS_PER_PAGE:
            raise CrawlError("parse_limit", "Osiągnięto limit elementów HTML")
        values = dict(attrs)
        if tag == "base" and self.base_href is None and values.get("href"):
            self.base_href = values["href"]
        pairs: list[tuple[str, LinkKind]] = []
        if tag in {"a", "area"}:
            pairs.append(("href", LinkKind.HYPERLINK))
        if self.mode != LinkSelection.HYPERLINKS and tag == "img":
            pairs.append(("src", LinkKind.IMAGE))
        if self.mode == LinkSelection.ALL_LINKS:
            if tag == "link":
                pairs.append(
                    (
                        "href",
                        LinkKind.STYLESHEET
                        if "stylesheet" in (values.get("rel") or "").lower().split()
                        else LinkKind.OTHER,
                    )
                )
            elif tag == "script":
                pairs.append(("src", LinkKind.SCRIPT))
            elif tag in {"audio", "video", "source", "track", "embed"}:
                pairs.append(("src", LinkKind.MEDIA))
                if tag == "video":
                    pairs.append(("poster", LinkKind.IMAGE))
            elif tag == "iframe":
                pairs.append(("src", LinkKind.OTHER))
            elif tag == "object":
                pairs.append(("data", LinkKind.OTHER))
            elif tag == "input" and (values.get("type") or "").lower() == "image":
                pairs.append(("src", LinkKind.IMAGE))
        for attribute, kind in pairs:
            value = values.get(attribute)
            if value:
                if len(self.references) >= MAX_LINKS_PER_PAGE:
                    raise CrawlError("link_limit", "Osiągnięto limit odnośników na stronie")
                self.references.append((value.strip(), kind))

    handle_startendtag = handle_starttag


def discover(
    body: bytes,
    final_url: str,
    mode: LinkSelection,
    encoding: str = "utf-8",
    *,
    cancelled: threading.Event | None = None,
    time_budget: float = 5,
) -> list[Reference]:
    parser = DiscoveryParser(mode)
    try:
        text = body.decode(encoding, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    deadline = time.monotonic() + time_budget
    fed = 0
    try:
        for position in range(0, len(text), 8192):
            if (cancelled is not None and cancelled.is_set()) or time.monotonic() > deadline:
                raise CrawlError("parse_timeout", "Przerwano analizę odnośników HTML")
            chunk = text[position : position + 8192]
            fed += len(chunk)
            parser.feed(chunk)
            # Python versions buffer feed fragments differently; count consumed characters.
            if fed - parser.consumed > MAX_UNFINISHED_TAG:
                raise CrawlError("parse_limit", "Zbyt długi niedomknięty element HTML")
    except (ValueError, AssertionError) as error:
        raise CrawlError("invalid_html", "Nieprawidłowa struktura HTML") from error
    base = final_url
    if parser.base_href:
        try:
            base = normalize_url(parser.base_href, final_url)
        except CrawlError:
            pass
    result = []
    for value, kind in parser.references:
        try:
            result.append(Reference(normalize_url(value, base), kind))
        except CrawlError:
            continue
    return result
