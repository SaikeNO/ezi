import asyncio
import itertools
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analysis import datasets, experiments, report
from .core import Config, Engine, Store, csv_export, now, sqlite_export

ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"


def create_app(db_path=None):
    store = Store(db_path or os.environ.get("EZI_DB", str(BACKEND_ROOT / "data" / "ezi.sqlite")))
    engine = Engine(store)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.cancelled.set()
        if engine.busy:
            try:
                await asyncio.wait_for(asyncio.shield(engine.task), 3)
            except asyncio.TimeoutError:
                engine.task.cancel()
                await asyncio.gather(engine.task, return_exceptions=True)

    app = FastAPI(title="EZI · Laboratorium WWW", lifespan=lifespan)
    app.state.store, app.state.engine = store, engine

    def get_session(session_id):
        rows = store.query("SELECT * FROM sessions WHERE id=?", (session_id,))
        if not rows:
            raise HTTPException(404, "Nie znaleziono sesji.")
        return rows[0]

    def get_run(run_id):
        try:
            return store.get_run(run_id)
        except KeyError:
            raise HTTPException(404, "Nie znaleziono przebiegu.")

    def available():
        if engine.busy:
            raise HTTPException(409, "Badanie już trwa. Zatrzymaj je lub poczekaj.")

    class SessionInput(BaseModel):
        name: str = Field(default="Nowe badanie WWW", min_length=1, max_length=150)
        config: Config

    @app.get("/api/status")
    def status():
        return {"busy": engine.busy, "active_run": engine.active_run}

    @app.get("/api/sessions")
    def sessions():
        return store.query("SELECT * FROM sessions ORDER BY created DESC")

    @app.post("/api/sessions", status_code=201)
    def create_session(body: SessionInput):
        session_id = uuid.uuid4().hex
        store.execute("INSERT INTO sessions VALUES(?,?,?,?)", (session_id, body.name, body.config.url, now()))
        return get_session(session_id)

    @app.get("/api/sessions/{session_id}")
    def session_detail(session_id: str):
        return get_session(session_id)

    @app.post("/api/sessions/{session_id}/runs", status_code=202)
    async def start_run(session_id: str, config: Config):
        session = get_session(session_id)
        available()
        if config.url != session["url"]:
            raise HTTPException(422, "Adres musi być zgodny z sesją. Dla nowego adresu utwórz sesję.")
        run_id = store.create_run(session_id, config)
        engine.start([run_id])
        return {"run_ids": [run_id]}

    @app.post("/api/sessions/{session_id}/experiments", status_code=202)
    async def start_experiments(session_id: str, config: Config):
        session = get_session(session_id)
        available()
        config = config.model_copy(update={"url": session["url"]})
        batch_id = uuid.uuid4().hex
        ids = [store.create_run(session_id, config.model_copy(update={"strategy": strategy, "scope": scope, "links": links}), "experiment", batch_id)
               for strategy, scope, links in itertools.product(("dfs", "bfs"), ("server", "web"), ("hyperlinks", "images", "all"))]
        engine.start(ids)
        return {"run_ids": ids, "batch_id": batch_id}

    @app.post("/api/sessions/{session_id}/datasets", status_code=202)
    async def start_datasets(session_id: str, config: Config):
        session = get_session(session_id)
        available()
        config = config.model_copy(update={"url": session["url"], "strategy": "bfs", "links": "hyperlinks"})
        ids = [store.create_run(session_id, config.model_copy(update={"depth": 2, "scope": "web"}), "dataset_A"),
               store.create_run(session_id, config.model_copy(update={"depth": 3, "scope": "server"}), "dataset_B")]
        engine.start(ids)
        return {"run_ids": ids}

    @app.post("/api/cancel")
    async def cancel():
        engine.cancelled.set()
        return {"message": "Zatrzymywanie bieżącego badania i kolejki."}

    @app.get("/api/sessions/{session_id}/comparison")
    def comparison(session_id: str):
        get_session(session_id)
        return experiments(store, session_id)

    @app.get("/api/sessions/{session_id}/datasets")
    def dataset_comparison(session_id: str):
        get_session(session_id)
        return datasets(store, session_id)

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str):
        return {**get_run(run_id), "metrics": store.metrics(run_id)}

    @app.get("/api/runs/{run_id}/graph")
    def graph(run_id: str):
        get_run(run_id)
        return store.graph(run_id)

    @app.get("/api/runs/{run_id}/records")
    def records(run_id: str):
        get_run(run_id)
        return store.records(run_id)

    @app.get("/api/runs/{run_id}/export.csv")
    def export_csv(run_id: str, fields: str = Query(default="URL,Keyword")):
        get_run(run_id)
        try:
            data = csv_export(store, run_id, fields.split(","))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return Response(data, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{run_id}.csv"'})

    @app.get("/api/runs/{run_id}/export.sqlite")
    def export_sqlite(run_id: str):
        get_run(run_id)
        return Response(sqlite_export(store, run_id), media_type="application/vnd.sqlite3", headers={"Content-Disposition": f'attachment; filename="{run_id}.sqlite"'})

    @app.get("/api/sessions/{session_id}/report", response_class=HTMLResponse)
    def export_report(session_id: str, download: bool = False):
        get_session(session_id)
        headers = {"Content-Disposition": 'attachment; filename="raport-ezi.html"'} if download else {}
        return HTMLResponse(report(store, session_id), headers=headers)

    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    else:
        @app.get("/", response_class=HTMLResponse)
        def missing_build():
            return '<html lang="pl"><meta charset="utf-8"><h1>EZI</h1><p>Uruchom setup.ps1, aby zbudować interfejs.</p><a href="/docs">Dokumentacja API</a></html>'
    return app
