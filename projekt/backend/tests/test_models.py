from datetime import UTC

import pytest
from alembic import command
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import build_engine
from app.models import Base, CrawlConfig, CrawlSession, Experiment, Link, LinkKind, Page
from app.schemas import CrawlConfigInput


def crawl(url="https://example.com/"):
    return CrawlSession(start_url=url, config=CrawlConfig(**CrawlConfigInput().model_dump()))


def page(session_id, url, depth=0):
    return Page(
        session_id=session_id, normalized_url=url, original_url=url, depth=depth, discovery_order=0
    )


def test_migrations_round_trip_and_metadata(database):
    settings, config = database
    engine = build_engine(settings.database_url)
    with engine.connect() as connection:
        assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
            "alembic_version"
        }
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002_sessions"
        assert {index["name"] for index in inspect(connection).get_indexes("sessions")} == {
            "ix_sessions_created_at_id",
            "ix_sessions_status_created_at",
        }
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()
    command.check(config)
    command.downgrade(config, "0001_bootstrap")
    engine = build_engine(settings.database_url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.check(config)


@pytest.mark.parametrize("load_children", [False, True])
def test_relationships_duplicate_links_and_cascade(database, load_children):
    settings, _ = database
    engine = build_engine(settings.database_url)
    with Session(engine) as db:
        first, other = crawl(), crawl()
        experiment = Experiment(
            name="Fixture experiment", start_url=first.start_url, sessions=[first, other]
        )
        db.add(experiment)
        db.flush()
        source, target = (
            page(first.id, first.start_url),
            page(first.id, first.start_url + "target", 1),
        )
        db.add_all([source, target])
        db.flush()
        for _ in range(2):
            db.add(
                Link(
                    session_id=first.id,
                    source_page_id=source.id,
                    target_page_id=target.id,
                    target_url=target.normalized_url,
                    kind=LinkKind.HYPERLINK,
                )
            )
        db.commit()
        first_id, other_id, experiment_id = first.id, other.id, experiment.id
        assert first.created_at.tzinfo == UTC
        assert len(source.outgoing_links) == 2
        assert source.outgoing_links[0].source_page.id == source.id
        assert source.outgoing_links[0].target_page.id == target.id
    with Session(engine) as db:
        first = db.get(CrawlSession, first_id)
        if load_children:
            assert len(first.pages) == 2 and len(first.links) == 2
            assert first.config and first.experiments
        db.delete(first)
        db.commit()
        assert db.get(CrawlSession, first_id) is None
        assert db.get(CrawlSession, other_id) is not None
        for model in [Page, Link]:
            assert db.scalar(select(func.count()).select_from(model)) == 0
        assert db.scalar(select(func.count()).select_from(CrawlConfig)) == 1
        assert [item.id for item in db.get(Experiment, experiment_id).sessions] == [other_id]
    engine.dispose()


def test_page_uniqueness_is_per_session(database):
    settings, _ = database
    engine = build_engine(settings.database_url)
    with Session(engine) as db:
        first, second = crawl(), crawl()
        db.add_all([first, second])
        db.flush()
        db.add_all([page(first.id, first.start_url), page(second.id, second.start_url)])
        db.commit()
        db.add(page(first.id, first.start_url))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    engine.dispose()


@pytest.mark.parametrize("cross_source", [True, False])
def test_links_cannot_reference_other_session(database, cross_source):
    settings, _ = database
    engine = build_engine(settings.database_url)
    with Session(engine) as db:
        first, second = crawl(), crawl()
        db.add_all([first, second])
        db.flush()
        source, target = page(first.id, first.start_url), page(second.id, second.start_url)
        db.add_all([source, target])
        db.flush()
        db.add(
            Link(
                session_id=first.id,
                source_page_id=target.id if cross_source else source.id,
                target_page_id=None if cross_source else target.id,
                target_url=target.normalized_url,
                kind=LinkKind.HYPERLINK,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    engine.dispose()


def test_deleting_target_preserves_discovered_link(database):
    settings, _ = database
    engine = build_engine(settings.database_url)
    with Session(engine) as db:
        first = crawl()
        db.add(first)
        db.flush()
        source, target = page(first.id, first.start_url), page(first.id, first.start_url + "target")
        db.add_all([source, target])
        db.flush()
        link = Link(
            session_id=first.id,
            source_page_id=source.id,
            target_page_id=target.id,
            target_url=target.normalized_url,
            kind=LinkKind.HYPERLINK,
        )
        db.add(link)
        db.commit()
        db.delete(target)
        db.commit()
        db.refresh(link)
        assert link.target_page_id is None and link.target_url.endswith("target")
    engine.dispose()


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE sessions SET status='invented'",
        "UPDATE sessions SET fetched_count=-1",
        "UPDATE crawl_config SET strategy='random'",
        "UPDATE crawl_config SET max_pages=0",
        "UPDATE crawl_config SET respect_robots=2",
    ],
)
def test_database_constraints(database, sql):
    settings, _ = database
    engine = build_engine(settings.database_url)
    with Session(engine) as db:
        db.add(crawl())
        db.commit()
        with pytest.raises(IntegrityError):
            db.execute(text(sql))
            db.commit()
        db.rollback()
    engine.dispose()


def test_deleting_experiment_keeps_sessions(database):
    settings, _ = database
    engine = build_engine(settings.database_url)
    with Session(engine) as db:
        session = crawl()
        experiment = Experiment(name="Fixture", start_url=session.start_url, sessions=[session])
        db.add(experiment)
        db.commit()
        session_id = session.id
        db.delete(experiment)
        db.commit()
        assert db.get(CrawlSession, session_id) is not None
        assert db.execute(text("SELECT * FROM experiment_sessions")).all() == []
    engine.dispose()
