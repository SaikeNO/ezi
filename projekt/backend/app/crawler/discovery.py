import codecs
import threading
import time
from dataclasses import dataclass
from html.parser import HTMLParser

from bs4.dammit import EncodingDetector

from app.crawler.urls import CrawlError, normalize_url
from app.models import LinkKind, LinkSelection

MAX_LINKS_PER_PAGE = 5000
MAX_TAGS_PER_PAGE = 100000
MAX_UNFINISHED_TAG = 65536
TEXT_BREAKS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}


@dataclass(frozen=True)
class Reference:
    url: str
    kind: LinkKind


@dataclass(frozen=True)
class Extraction:
    url: str
    encoding: str
    title: str | None
    description: str | None
    keywords: str | None
    body: str
    references: list[Reference]


def decode_html(body: bytes, encoding: str | None) -> tuple[str, str]:
    """Deterministic BOM > HTTP charset > HTML declaration > UTF-8 replacement."""
    bom = next(
        (
            name
            for prefix, name in (
                (codecs.BOM_UTF32_LE, "utf-32"),
                (codecs.BOM_UTF32_BE, "utf-32"),
                (codecs.BOM_UTF8, "utf-8-sig"),
                (codecs.BOM_UTF16_LE, "utf-16"),
                (codecs.BOM_UTF16_BE, "utf-16"),
            )
            if body.startswith(prefix)
        ),
        None,
    )
    declared = EncodingDetector.find_declared_encoding(body[:4096], is_html=True)
    for candidate in (bom, encoding, declared, "utf-8"):
        if not candidate:
            continue
        try:
            name = codecs.lookup(candidate).name
            return body.decode(name, errors="replace"), name
        except (LookupError, UnicodeError, ValueError):
            continue
    return body.decode("utf-8", errors="replace"), "utf-8"


class DiscoveryParser(HTMLParser):
    """Bounded, non-executing HTML extraction; no browser DOM repair or rendering."""

    def __init__(self, mode: LinkSelection):
        super().__init__(convert_charrefs=True)
        self.mode = mode
        self.references: list[tuple[str, LinkKind]] = []
        self.base_href: str | None = None
        self.tags = 0
        self.consumed = 0
        self.title_parts: list[str] | None = None
        self.in_title = False
        self.description: str | None = None
        self.keywords: str | None = None
        self.hidden: list[str] = []
        self.text_parts: list[str] = []
        self.body_parts: list[str] = []
        self.has_body = False
        self.in_body = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if not self.hidden and not self.in_title:
            self.text_parts.append(data)
            if self.in_body:
                self.body_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in TEXT_BREAKS:
            self.handle_data(" ")
        if tag in {"title", "head", "body"}:
            self.in_title = False
        if tag == "body":
            self.in_body = False
        if tag in self.hidden:
            index = len(self.hidden) - 1 - self.hidden[::-1].index(tag)
            del self.hidden[index:]

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def updatepos(self, start: int, end: int) -> int:
        result = super().updatepos(start, end)
        self.consumed += end - start
        return result

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags += 1
        if self.tags > MAX_TAGS_PER_PAGE:
            raise CrawlError("parse_limit", "Osiągnięto limit elementów HTML")
        values = dict(attrs)
        if tag in TEXT_BREAKS:
            self.handle_data(" ")
        if tag == "body":
            self.has_body = self.in_body = True
            self.in_title = False
            self.hidden.clear()  # Recover from an omitted </head>.
        if tag == "title" and self.title_parts is None:
            self.title_parts = []
            self.in_title = True
        if tag in {"head", "title", "script", "style", "template", "noscript"}:
            self.hidden.append(tag)
        if tag == "meta":
            name = (values.get("name") or "").strip().lower()
            if name in {"description", "keywords"} and getattr(self, name) is None:
                content = values.get("content")
                if content is not None:
                    setattr(self, name, " ".join(content.split()))
        if tag == "base" and self.base_href is None and values.get("href") is not None:
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


def extract(
    body: bytes,
    final_url: str,
    mode: LinkSelection,
    encoding: str | None = None,
    *,
    cancelled: threading.Event | None = None,
    time_budget: float = 5,
) -> Extraction:
    parser = DiscoveryParser(mode)
    deadline = time.monotonic() + time_budget
    if cancelled is not None and cancelled.is_set():
        raise CrawlError("parse_timeout", "Przerwano analizę HTML")
    text, detected_encoding = decode_html(body, encoding)
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
        parser.close()
    except (ValueError, AssertionError) as error:
        raise CrawlError("invalid_html", "Nieprawidłowa struktura HTML") from error
    base = final_url
    if parser.base_href:
        try:
            base = normalize_url(parser.base_href, final_url)
        except CrawlError:
            pass
    result = []
    for index, (value, kind) in enumerate(parser.references):
        if index % 64 == 0 and (
            (cancelled is not None and cancelled.is_set()) or time.monotonic() > deadline
        ):
            raise CrawlError("parse_timeout", "Przerwano analizę HTML")
        try:
            result.append(Reference(normalize_url(value, base), kind))
        except CrawlError:
            continue
    if (cancelled is not None and cancelled.is_set()) or time.monotonic() > deadline:
        raise CrawlError("parse_timeout", "Przerwano analizę HTML")
    return Extraction(
        normalize_url(final_url),
        detected_encoding,
        " ".join("".join(parser.title_parts).split()) if parser.title_parts is not None else None,
        parser.description,
        parser.keywords,
        " ".join("".join(parser.body_parts if parser.has_body else parser.text_parts).split()),
        result,
    )


def discover(
    body: bytes,
    final_url: str,
    mode: LinkSelection,
    encoding: str | None = None,
    *,
    cancelled: threading.Event | None = None,
    time_budget: float = 5,
) -> list[Reference]:
    """Compatibility entry point for callers needing references only."""
    return extract(
        body, final_url, mode, encoding, cancelled=cancelled, time_budget=time_budget
    ).references
