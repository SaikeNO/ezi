from sqlalchemy.orm import Session

from app.models import CrawlEvent, CrawlSession


def snapshot(crawl: CrawlSession) -> dict:
    return {
        "session_id": crawl.id,
        "status": crawl.status.value,
        "discovered_count": crawl.discovered_count,
        "fetched_count": crawl.fetched_count,
        "error_count": crawl.error_count,
        "link_count": crawl.link_count,
        "stop_reason": crawl.stop_reason,
        "error": crawl.error,
    }


def record(db: Session, crawl: CrawlSession, kind: str, **extra) -> None:
    db.add(CrawlEvent(session_id=crawl.id, kind=kind, data={**snapshot(crawl), **extra}))
