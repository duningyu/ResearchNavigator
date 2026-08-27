"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from research_navigator.analysis.providers import build_analysis_provider
from research_navigator.backups.service import apply_pending_restore
from research_navigator.config import Settings
from research_navigator.db import Database
from research_navigator.routes import (
    analysis,
    authors,
    auth,
    backups,
    backfill,
    comparisons,
    clustering,
    datasets,
    documents,
    evidence,
    evaluations,
    gaps,
    library,
    plans,
    projects,
    recommendations,
    search,
    selections,
    system,
    workspace,
)
from research_navigator.routes import (
    settings as settings_routes,
)
from research_navigator.open_access import build_open_access_resolver, build_pdf_fetcher
from research_navigator.scholarly.service import build_search_service


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved.ensure_directories()
        apply_pending_restore(resolved)
        database = Database.from_url(resolved.database_url)
        database.init()
        app.state.settings = resolved
        app.state.database = database
        app.state.search_service = build_search_service(resolved)
        app.state.oa_resolver = build_open_access_resolver(resolved)
        app.state.pdf_fetcher = build_pdf_fetcher(resolved)
        app.state.analysis_provider = build_analysis_provider(resolved)
        runtime_config_path = resolved.data_dir / "admin_runtime_config.json"
        runtime_config = {"source_health_timeout_seconds": 5.0, "worker_max_attempts_default": 3}
        if runtime_config_path.exists():
            import json

            try:
                stored = json.loads(runtime_config_path.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    runtime_config.update(
                        {key: stored[key] for key in runtime_config if key in stored}
                    )
            except (OSError, ValueError, TypeError):
                pass
        app.state.runtime_config = runtime_config
        yield
        database.dispose()

    app = FastAPI(
        title="ResearchNavigator API",
        version="2.2.0",
        description="Evidence-grounded research direction and paper workspace.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        try:
            with app.state.database.engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
            database_status = "ok"
        except Exception:
            database_status = "error"
        return {
            "status": "ok" if database_status == "ok" else "degraded",
            "version": "2.2.0",
            "database": database_status,
        }

    app.include_router(auth.router, prefix="/api")
    app.include_router(backups.router, prefix="/api")
    app.include_router(backfill.router, prefix="/api")
    app.include_router(projects.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(selections.router, prefix="/api")
    app.include_router(settings_routes.router, prefix="/api")
    app.include_router(library.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(evidence.router, prefix="/api")
    app.include_router(evaluations.router, prefix="/api")
    app.include_router(analysis.router, prefix="/api")
    app.include_router(authors.router, prefix="/api")
    app.include_router(comparisons.router, prefix="/api")
    app.include_router(clustering.router, prefix="/api")
    app.include_router(datasets.router, prefix="/api")
    app.include_router(gaps.router, prefix="/api")
    app.include_router(plans.router, prefix="/api")
    app.include_router(recommendations.router, prefix="/api")
    app.include_router(workspace.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    return app


app = create_app()
