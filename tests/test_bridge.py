"""Tests for ``bridge/bridge.py`` — the run_bridge streaming/keep-alive loop.

Uses fake client/server stand-ins (no BLE, no sockets) to exercise the
data-gap keep-alive: a link-up gap re-sends the emitter's "?" gap line so
TestController stays connected, while healthy streaming and link-down do not.
"""
import asyncio

import pytest

from brymen.parsers import StreamFrame

from bridge.bridge import run_bridge
from bridge.emitter import Emitter


def run(coro):
    return asyncio.run(coro)


class FakeServer:
    """Records lines sent to clients (no real sockets)."""

    def __init__(self):
        self.host = "0.0.0.0"
        self.bound_port = 6000
        self.lines = []
        self.started = False
        self.closed = False

    async def start(self):
        self.started = True

    async def send(self, line: str) -> None:
        self.lines.append(line)

    async def close(self):
        self.closed = True


class FakeClient:
    """A BrymenClient stand-in: yields ``frames`` once, then a link-up gap.

    ``is_connected`` is a plain attribute so a test can simulate a link drop
    (power-off): after ``drop_after`` frames are yielded it flips to False.
    """

    def __init__(self, frames=(), connected=True, drop_after=0):
        self.frames = list(frames)
        self.is_connected = connected
        self.closed = False
        self._drop_after = drop_after
        self._yielded = 0

    async def ensure_connected(self, retries=None, on_retry=None):
        self.is_connected = True

    async def read_stream(self, **kwargs):
        for frame in self.frames:
            yield frame
            self._yielded += 1
            if self._drop_after and self._yielded >= self._drop_after:
                self.is_connected = False
        # Link-up gap: never yield again (the keep-alive should kick in).
        await asyncio.Event().wait()

    async def close(self):
        self.closed = True


def _frame(readings):
    return StreamFrame(info=None, readings=readings)


def _run_bridge_until(client, server, seconds, keepalive_interval=0.05):
    """Run run_bridge with fakes for ``seconds``, then cancel it."""
    async def _run():
        task = asyncio.create_task(
            run_bridge(
                "00:11:22:33:44:55", "0000", server, Emitter(),
                keepalive_interval=keepalive_interval,
                client_factory=lambda: client,
            )
        )
        try:
            await asyncio.sleep(seconds)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    run(_run())


def test_keepalive_sends_gap_lines_during_link_up_gap(make_reading):
    # One frame arrives (last_reading set), then a link-up gap: the keep-alive
    # re-sends "DCV ? " every interval so TestController doesn't drop.
    client = FakeClient(frames=[_frame([make_reading()])])
    server = FakeServer()
    _run_bridge_until(client, server, 0.3)
    assert server.lines[0] == "DCV 607.80"
    assert any(line == "DCV ? " for line in server.lines[1:])


def test_no_keepalive_before_first_frame(make_reading):
    # No frame ever -> last_reading is None -> no gap lines.
    client = FakeClient(frames=[])
    server = FakeServer()
    _run_bridge_until(client, server, 0.2)
    assert server.lines == []


def test_no_keepalive_when_link_down(make_reading):
    # A frame arrives, then the link drops (is_connected False) -> the
    # keep-alive must NOT keep feeding TC a stale "?".
    client = FakeClient(frames=[_frame([make_reading()])], drop_after=1)
    server = FakeServer()
    _run_bridge_until(client, server, 0.2)
    assert server.lines == ["DCV 607.80"]


def test_keepalive_disabled_when_interval_zero(make_reading):
    # keepalive_interval <= 0 disables the keep-alive entirely.
    client = FakeClient(frames=[_frame([make_reading()])])
    server = FakeServer()
    _run_bridge_until(client, server, 0.2, keepalive_interval=0)
    assert server.lines == ["DCV 607.80"]
