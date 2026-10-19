from pathlib import Path
from typing import Self
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite:///./data/webcrawler.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS origins must be HTTP(S) origins without paths")
            try:
                _ = parsed.port
            except ValueError as error:
                raise ValueError("Invalid CORS origin port") from error
        return origins

    @model_validator(mode="after")
    def resolve_database(self) -> Self:
        try:
            url = make_url(self.database_url)
        except ArgumentError as error:
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy SQLite URL") from error
        if url.drivername != "sqlite" or url.host or not url.database or url.query:
            raise ValueError("DATABASE_URL must point to a SQLite file or :memory:")
        if url.database != ":memory:":
            path = Path(url.database)
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            url = url.set(database=path.resolve().as_posix())
        self.database_url = url.render_as_string(hide_password=False)
        return self
