from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.core.config import PROJECT_ROOT, Settings
from app.database import build_engine
from app.main import create_app


def settings_for(path: Path) -> Settings:
    return Settings(_env_file=None, database_url=f"sqlite:///{path.as_posix()}")


def test_health_checks_sqlite_and_creates_parent(tmp_path):
    path = tmp_path / "nested" / "test.db"
    with TestClient(create_app(settings_for(path))) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert path.is_file()


def test_health_failure_is_503_without_database_details(tmp_path, monkeypatch):
    app = create_app(settings_for(tmp_path / "test.db"))

    def fail():
        raise OperationalError("private db path", {}, Exception("secret"))

    monkeypatch.setattr(app.state.engine, "connect", fail)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
    assert "secret" not in response.text


@pytest.mark.parametrize(
    "origin,allowed",
    [
        ("http://localhost:5173", True),
        ("http://127.0.0.1:5173", True),
        ("https://untrusted.example", False),
    ],
)
def test_cors(tmp_path, origin, allowed):
    with TestClient(create_app(settings_for(tmp_path / "test.db"))) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == (200 if allowed else 400)
    assert response.headers.get("access-control-allow-origin") == (origin if allowed else None)


@pytest.mark.parametrize(
    "origin", ["*", "ftp://localhost", "http://localhost/path", "http://u:p@localhost"]
)
def test_reject_invalid_cors_origin(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=[origin])


def test_sqlite_configuration():
    settings = Settings(_env_file=None, database_url="sqlite:///./data/example.db")
    assert Path(make_url(settings.database_url).database) == PROJECT_ROOT / "data" / "example.db"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql://localhost/test")


def test_migrations_upgrade_downgrade_and_persist(tmp_path, monkeypatch):
    path = tmp_path / "migrations.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path.as_posix()}")
    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    engine = build_engine(settings_for(path).database_url)
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001_bootstrap"
        )
        assert inspect(connection).get_table_names() == ["alembic_version"]
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
    engine.dispose()
    command.downgrade(config, "base")
    engine = build_engine(settings_for(path).database_url)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM alembic_version")) == 0
    engine.dispose()
    command.upgrade(config, "head")


@pytest.mark.parametrize(
    "url", ["invalid", "sqlite://", "sqlite://host/db", "sqlite:///test.db?mode=ro"]
)
def test_reject_invalid_database_url(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=url)


def test_dotenv_and_working_directory_independence(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=sqlite:///./data/from-env.db\n"
        'CORS_ORIGINS=["http://localhost:4321"]\n'
        "VITE_API_BASE_URL=http://localhost:8000\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=env_file)
    assert Path(make_url(settings.database_url).database) == PROJECT_ROOT / "data" / "from-env.db"
    assert settings.cors_origins == ["http://localhost:4321"]
