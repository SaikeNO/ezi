import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import PROJECT_ROOT, Settings
from app.main import create_app


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "sessions.db"
    url = f"sqlite:///{path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    command.upgrade(config, "head")
    settings = Settings(_env_file=None, database_url=url)
    return settings, config


@pytest.fixture
def client(database):
    settings, _ = database
    with TestClient(create_app(settings)) as client:
        yield client
