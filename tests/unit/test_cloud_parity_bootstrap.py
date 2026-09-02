from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI


@asynccontextmanager
async def _lifespan(app: FastAPI):
    app.state.started = True
    try:
        yield
    finally:
        app.state.stopped = True


def test_fastapi_lifespan_requires_async_context_manager() -> None:
    app = FastAPI(lifespan=_lifespan)
    context = app.router.lifespan_context(app)

    with pytest.raises(TypeError, match="context manager protocol"), context:  # type: ignore[abstract]
        pass


@pytest.mark.asyncio
async def test_parity_lifespan_scope_runs_startup_and_shutdown() -> None:
    app = FastAPI(lifespan=_lifespan)

    async with app.router.lifespan_context(app):
        assert app.state.started is True
        assert not hasattr(app.state, "stopped")

    assert app.state.stopped is True


@pytest.mark.asyncio
async def test_parity_lifespan_shutdown_runs_on_controlled_error() -> None:
    app = FastAPI(lifespan=_lifespan)

    with pytest.raises(RuntimeError, match="synthetic parity failure"):
        async with app.router.lifespan_context(app):
            raise RuntimeError("synthetic parity failure")

    assert app.state.stopped is True
