import os
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.engine import make_url


class WorkerOwnership:
    """One background worker process per SQLite file, including on Windows."""

    def __init__(self, database_url: str):
        database = make_url(database_url).database
        self.path = Path(database + ".worker.lock") if database and database != ":memory:" else None
        self.handle: BinaryIO | None = None

    def acquire(self) -> None:
        if self.path is None:
            return
        handle = self.path.open("a+b")
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            raise RuntimeError(
                "SQLite crawler requires exactly one API worker per database"
            ) from error
        self.handle = handle

    def release(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None
