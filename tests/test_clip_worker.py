"""Daemon-thread asyncio host smoke tests (fake runtime, no BLE)."""

import asyncio
import threading
import time

from backend.clip.worker import ClipWorker


class FakeRuntime:
    """Minimal runtime: run_forever blocks until shutdown()."""

    def __init__(self):
        self._stop: asyncio.Event | None = None
        self.shutdown_called = threading.Event()

    async def run_forever(self):
        self._stop = asyncio.Event()
        await self._stop.wait()

    async def shutdown(self):
        self.shutdown_called.set()
        if self._stop is not None:
            self._stop.set()

    async def status_payload(self):
        return {"connected": False, "device_id": "fake"}


def test_worker_start_dispatch_stop():
    worker = ClipWorker(runtime_factory=FakeRuntime)
    worker.start()
    try:
        assert worker.running
        runtime = worker.runtime
        assert runtime is not None
        assert isinstance(runtime, FakeRuntime)

        payload = worker.call(runtime.status_payload(), timeout=5)
        assert payload == {"connected": False, "device_id": "fake"}
    finally:
        worker.stop()
    assert not worker.running
    assert runtime.shutdown_called.is_set()  # type: ignore[union-attr]


def test_worker_call_before_start_raises():
    worker = ClipWorker(runtime_factory=FakeRuntime)
    from backend.clip.exceptions import ClipUnavailableError

    try:
        # No coroutine-friendly way to call before start; verify via status()
        try:
            worker.get_status()
            assert False, "expected unavailable error"
        except ClipUnavailableError:
            pass
    finally:
        worker.stop()


def test_worker_stop_wakes_run_forever_quickly():
    worker = ClipWorker(runtime_factory=FakeRuntime)
    worker.start()
    start = time.monotonic()
    worker.stop()
    assert time.monotonic() - start < 5.0
