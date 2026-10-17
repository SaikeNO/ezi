import pytest
from .fixture_site import sites
from backend.core import Config, Engine, Store, now


@pytest.fixture(scope="session")
def site():
    with sites() as result:
        yield result


@pytest.fixture
def store(tmp_path, site):
    s = Store(tmp_path / "test.sqlite")
    s.execute("INSERT INTO sessions VALUES('session','Test',?,?)", (site[0]+"/", now()))
    return s


@pytest.fixture
def crawl(store, site):
    async def run(**kwargs):
        config = Config(**{"url":site[0]+"/", "delay":0, "timeout":1, **kwargs})
        run_id = store.create_run("session", config)
        engine = Engine(store)
        await engine.crawl(run_id)
        return run_id
    return run
