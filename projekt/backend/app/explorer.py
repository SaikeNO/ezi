import csv
import io
import tempfile
import time
import unicodedata
from enum import StrEnum
from typing import Annotated, BinaryIO

from fastapi import HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.models import Page

MAX_EXPORT_BYTES = 64 * 1024 * 1024
MAX_EXPORT_SECONDS = 30


class PageFilters(BaseModel):
    q: str = ""
    depth: int | None = None
    fetched: bool | None = None
    has_error: bool | None = None
    http_status: int | None = None

    def predicates(self, session_id: str) -> list[ColumnElement[bool]]:
        result = [Page.session_id == session_id]
        if self.q:
            result.append(
                or_(
                    *(
                        func.instr(func.casefold(column), self.q.casefold()) > 0
                        for column in (
                            Page.normalized_url,
                            Page.final_url,
                            Page.title,
                            Page.description,
                            Page.keywords,
                        )
                    )
                )
            )
        if self.depth is not None:
            result.append(Page.depth == self.depth)
        if self.fetched is not None:
            result.append(Page.final_url.is_not(None) if self.fetched else Page.final_url.is_(None))
        if self.has_error is not None:
            result.append(Page.error.is_not(None) if self.has_error else Page.error.is_(None))
        if self.http_status is not None:
            result.append(Page.http_status == self.http_status)
        return result


def page_filters(
    q: Annotated[str, Query(max_length=200)] = "",
    depth: Annotated[int | None, Query(ge=0, le=21)] = None,
    fetched: bool | None = None,
    has_error: bool | None = None,
    http_status: Annotated[int | None, Query(ge=100, le=599)] = None,
) -> PageFilters:
    return PageFilters(
        q=q.strip(), depth=depth, fetched=fetched, has_error=has_error, http_status=http_status
    )


class Separator(StrEnum):
    COMMA = "comma"
    SEMICOLON = "semicolon"
    TAB = "tab"


EXPORT_FIELDS = {
    "url": ("URL", Page.normalized_url),
    "keywords": ("Keyword", Page.keywords),
    "title": ("Title", Page.title),
    "description": ("Description", Page.description),
    "body": ("Body", Page.body),
    "original_url": ("Original URL", Page.original_url),
    "final_url": ("Final URL", Page.final_url),
    "depth": ("Depth", Page.depth),
    "http_status": ("HTTP Status", Page.http_status),
    "content_type": ("Content-Type", Page.content_type),
    "encoding": ("Encoding", Page.encoding),
    "error": ("Error", Page.error),
}


def export_fields(fields: Annotated[str, Query(max_length=300)] = "url,keywords") -> list[str]:
    selected = [field.strip() for field in fields.split(",")]
    if (
        not selected
        or any(field not in EXPORT_FIELDS for field in selected)
        or len(selected) != len(set(selected))
    ):
        raise HTTPException(
            422,
            detail={
                "code": "invalid_export_fields",
                "message": "Wybierz niepowtarzające się pola eksportu z dozwolonej listy",
            },
        )
    return selected


def safe_cell(value: object) -> str:
    text = "" if value is None else str(value)
    # Keep original content; prefix before any whitespace/control/format disguise.
    significant = text.lstrip()
    index = 0
    while index < len(significant) and unicodedata.category(significant[index])[0] in {"C", "Z"}:
        index += 1
    significant = significant[index:].lstrip()
    if text.startswith(("\t", "\r", "\n")) or significant.startswith(
        ("=", "+", "-", "@", "＝", "＋", "－", "＠")
    ):
        return "'" + text
    return text


def prepare_csv(
    db: Session,
    session_id: str,
    filters: PageFilters,
    fields: list[str],
    separator: Separator,
    bom: bool,
) -> tuple[BinaryIO, int]:
    """Build bounded snapshot before HTTP headers; no partial successful downloads."""
    output = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    line = io.StringIO(newline="")
    writer = csv.writer(
        line,
        delimiter={Separator.COMMA: ",", Separator.SEMICOLON: ";", Separator.TAB: "\t"}[separator],
        lineterminator="\r\n",
    )
    deadline = time.monotonic() + MAX_EXPORT_SECONDS

    def write_row(values: list[str]) -> None:
        line.seek(0)
        line.truncate(0)
        writer.writerow(values)
        encoded = line.getvalue().encode("utf-8")
        if output.tell() + len(encoded) > MAX_EXPORT_BYTES:
            raise HTTPException(
                413,
                detail={
                    "code": "export_too_large",
                    "message": "Eksport przekracza 64 MiB. Wybierz mniej pól lub zawęź filtry.",
                },
            )
        if time.monotonic() > deadline:
            raise HTTPException(
                503,
                detail={
                    "code": "export_timeout",
                    "message": "Przekroczono czas eksportu. Zawęź filtry i spróbuj ponownie.",
                },
            )
        output.write(encoded)

    try:
        if bom:
            output.write(b"\xef\xbb\xbf")
        write_row([EXPORT_FIELDS[field][0] for field in fields])
        rows = db.execute(
            select(*(EXPORT_FIELDS[field][1] for field in fields))
            .where(*filters.predicates(session_id))
            .order_by(Page.discovery_order, Page.id)
        ).yield_per(1)
        for row in rows:
            write_row([safe_cell(value) for value in row])
        size = output.tell()
        output.seek(0)
        return output, size
    except BaseException:
        output.close()
        raise
    finally:
        line.close()
