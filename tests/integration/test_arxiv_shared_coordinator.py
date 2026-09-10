from __future__ import annotations

import asyncio
import multiprocessing
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from research_navigator.db import Database
from research_navigator.scholarly.arxiv import ArxivAdapter
from research_navigator.scholarly.base import SearchRequest
from research_navigator.scholarly.coordinator import (
    ArxivRequestCoordinator,
    CoordinatorUnavailable,
)

_FEED = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom'>
  <entry>
    <id>https://arxiv.org/abs/2608.12345</id>
    <title>Controlled arXiv result</title>
    <summary>Controlled evidence</summary>
    <published>2026-08-01T00:00:00Z</published>
  </entry>
</feed>"""


class _RecordingHandler(BaseHTTPRequestHandler):
    events: list[dict[str, float | str]] = []
    lock = threading.Lock()
    request_delay = 0.2

    def do_GET(self) -> None:  # noqa: N802 - stdlib protocol name
        started = time.monotonic()
        with self.lock:
            self.events.append({"kind": "start", "at": started})
        time.sleep(self.request_delay)
        self.send_response(200)
        self.send_header("Content-Type", "application/atom+xml")
        self.send_header("Content-Length", str(len(_FEED)))
        self.end_headers()
        self.wfile.write(_FEED)
        with self.lock:
            self.events.append({"kind": "end", "at": time.monotonic()})

    def log_message(self, *_args: object) -> None:
        return


def _worker(
    db_url: str, endpoint: str, start_event: object, result_queue: object, worker_id: str
) -> None:
    async def run() -> None:
        database = Database.from_url(db_url)
        coordinator = ArxivRequestCoordinator(database=database, owner_id=worker_id)
        adapter = ArxivAdapter(coordinator=coordinator)
        adapter.base_url = endpoint
        await asyncio.to_thread(start_event.wait)
        results = []
        for _ in range(2):
            result = await adapter.search(SearchRequest(query="controlled", limit=1))
            results.append(result.status.status)
        result_queue.put(results)
        database.dispose()

    asyncio.run(run())


@pytest.fixture()
def recording_server() -> tuple[str, _RecordingHandler]:
    _RecordingHandler.events = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api/query", _RecordingHandler
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_two_independent_processes_share_arxiv_lease_and_spacing(
    tmp_path: Path, recording_server: tuple[str, _RecordingHandler]
) -> None:
    endpoint, handler = recording_server
    db_path = tmp_path / "shared.sqlite"
    database = Database.from_url(f"sqlite+pysqlite:///{db_path}")
    database.init()
    database.dispose()

    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_worker,
            args=(
                f"sqlite+pysqlite:///{db_path}",
                endpoint,
                start_event,
                result_queue,
                f"worker-{index}",
            ),
        )
        for index in range(2)
    ]
    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    assert [result_queue.get(timeout=2) for _ in processes] == [["ok", "ok"], ["ok", "ok"]]
    starts = sorted(
        event["at"] for event in handler.events if event["kind"] == "start"
    )
    assert len(starts) == 4
    assert all(
        second - first >= 3.0 for first, second in zip(starts, starts[1:], strict=False)
    ), starts

    in_flight = 0
    maximum = 0
    for event in sorted(handler.events, key=lambda item: float(item["at"])):
        if event["kind"] == "start":
            in_flight += 1
            maximum = max(maximum, in_flight)
        else:
            in_flight -= 1
    assert maximum <= 1


def test_coordinator_lease_expiry_and_owner_safe_release(tmp_path: Path) -> None:
    db_path = tmp_path / "lease.sqlite"
    database = Database.from_url(f"sqlite+pysqlite:///{db_path}")
    database.init()
    current = [datetime(2026, 9, 7, tzinfo=UTC)]

    def clock() -> datetime:
        return current[0]

    first = ArxivRequestCoordinator(
        database=database, owner_id="first", clock=clock, lease_ttl_seconds=2
    )
    second = ArxivRequestCoordinator(
        database=database, owner_id="second", clock=clock, lease_ttl_seconds=2
    )
    assert first.try_acquire() is True
    assert second.try_acquire() is False
    assert second.release() is False
    current[0] += timedelta(seconds=3)
    assert second.try_acquire() is True
    assert first.release() is False
    assert second.release() is True
    database.dispose()


def test_coordinator_unavailable_fails_closed(tmp_path: Path) -> None:
    database = Database.from_url(f"sqlite+pysqlite:///{tmp_path / 'missing' / 'state.sqlite'}")
    coordinator = ArxivRequestCoordinator(database=database, acquire_timeout_seconds=0.1)
    with pytest.raises(CoordinatorUnavailable):
        coordinator.try_acquire()
    database.dispose()


def test_cancelled_request_releases_only_its_own_lease(tmp_path: Path) -> None:
    database = Database.from_url(f"sqlite+pysqlite:///{tmp_path / 'cancel.sqlite'}")
    database.init()
    first = ArxivRequestCoordinator(
        database=database,
        owner_id="first",
        minimum_interval_seconds=0.0,
        lease_ttl_seconds=5.0,
    )
    second = ArxivRequestCoordinator(
        database=database,
        owner_id="second",
        minimum_interval_seconds=0.0,
        lease_ttl_seconds=5.0,
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def operation() -> None:
        started.set()
        await release.wait()

    async def scenario() -> None:
        task = asyncio.create_task(first.run("search", operation))
        await started.wait()
        assert second.try_acquire() is False
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert second.try_acquire() is True
        assert second.release() is True

    asyncio.run(scenario())
    database.dispose()
