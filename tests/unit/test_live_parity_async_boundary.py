import asyncio
import threading

from deployment.cloud.parity import run_evidence_workflow_parity as parity


def test_run_once_async_uses_worker_thread(monkeypatch) -> None:
    caller_thread = threading.get_ident()
    observed: list[tuple[int, bool]] = []

    def fake_run_once(database, *, settings):
        try:
            loop_running = asyncio.get_running_loop().is_running()
        except RuntimeError:
            loop_running = False
        observed.append((threading.get_ident(), loop_running))
        return 42

    monkeypatch.setattr(parity, "run_once", fake_run_once)

    result = asyncio.run(parity._run_once_async(object(), settings=object()))

    assert result == 42
    assert observed
    assert observed[0][0] != caller_thread
    assert observed[0][1] is False
