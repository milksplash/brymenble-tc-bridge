"""Tie the Brymen SDK, the SingleValue emitter and a transport together.

Runnable directly as a script (e.g. the VS Code "Run Python File" button) or
as a module (``python -m bridge``); both launch the same CLI (``bridge.cli``).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import time

# Running this file as a script (``python bridge/bridge.py``) puts the
# script's directory on sys.path instead of the repo root, so the package
# imports below can't resolve. Detect that and add the repo root so both
# entry points work.
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brymen import BrymenClient

from bridge.emitter import Emitter
from bridge.transports import TcpLineServer

log = logging.getLogger(__name__)


def _on_retry(attempt: int, max_retries, error: Exception) -> None:
    """Log retry attempts (SDK calls this before each retry)."""
    if max_retries is None:
        log.warning("retry %d: %s (retrying until the meter returns)", attempt, error)
    else:
        log.warning("retry %d/%s: %s", attempt, max_retries, error)


async def run_bridge(
    mac: str,
    password: str,
    server: TcpLineServer,
    emitter: Emitter,
    pause_cap: float = 60.0,
    sync_rtc: bool = True,
    keepalive_interval: float = 0.5,
    client_factory=None,
) -> None:
    """Connect to the meter and stream SingleValue lines to ``server``.

    Runs until cancelled. The meter is reconnected forever (it may power off
    mid-test). ``pause_cap`` bounds how long a BLE-link-up silence is
    tolerated before a reconnect is forced anyway (e.g. the link-state report
    lags behind a real power-off). It maps onto ``BrymenClient.read_stream()``,
    which owns the pause-vs-power-off decision (using its ``no_data_timeout``
    default to check the link state).

    ``keepalive_interval`` is how long a link-up data gap (function/range
    switch — the meter blanks its display) may last before the bridge re-sends
    a "?" gap line to TestController, so TC doesn't time out and drop the
    socket (its reader closes after ~1.5-2 s of silence). The meter streams at
    ~5 Hz (~200 ms), so normal frames land well inside the interval and no gap
    lines are sent during healthy operation. ``keepalive_interval <= 0``
    disables the keep-alive.

    ``client_factory`` is a test seam: a zero-arg callable returning the
    ``BrymenClient`` (or a fake) to drive. Defaults to a real client for
    ``mac``/``password``/``sync_rtc``.
    """
    if client_factory is None:
        client_factory = lambda: BrymenClient(  # noqa: E731
            mac, password, sync_rtc_on_connect=sync_rtc
        )
    client = client_factory()
    last_reading = None
    last_sent = 0.0

    async def _keepalive() -> None:
        """Re-send a "?" gap line while the BLE link is up but no reading has
        been sent for ``keepalive_interval`` (e.g. mid function switch)."""
        nonlocal last_sent
        while True:
            await asyncio.sleep(keepalive_interval)
            if (
                client.is_connected
                and last_reading is not None
                and time.monotonic() - last_sent >= keepalive_interval
            ):
                await server.send(emitter.gap_line(last_reading))
                last_sent = time.monotonic()

    keepalive_task = None
    if keepalive_interval > 0:
        keepalive_task = asyncio.create_task(_keepalive())
    try:
        await server.start()
        log.info(
            "bridge listening on %s:%s — point TestController at #port %d "
            "(Socket interface)",
            server.host,
            server.bound_port,
            server.bound_port,
        )

        # Initial connect (retries forever until the meter is in range).
        await client.ensure_connected(retries=None, on_retry=_on_retry)
        log.info("connected to %s", mac)

        def _on_lost(reason: str) -> None:
            if reason == "pause_cap":
                log.warning(
                    "no data for %.0fs with link up — forcing reconnect",
                    pause_cap,
                )
            else:
                log.warning("BLE link lost — reconnecting")

        def _on_reconnected() -> None:
            log.info("reconnected to %s", mac)

        async for frame in client.read_stream(
            pause_cap=pause_cap,
            retries=None,
            on_retry=_on_retry,
            on_lost=_on_lost,
            on_reconnected=_on_reconnected,
        ):
            # Remember the last reading so the gap keep-alive can reuse its
            # mode token (the multi-mode def needs a valid column to show "?").
            for reading in frame.readings or ():
                if reading is not None:
                    last_reading = reading
                    break
            for line in emitter.format_frame(frame):
                await server.send(line)
                last_sent = time.monotonic()
    finally:
        if keepalive_task is not None:
            keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keepalive_task
        await client.close()
        await server.close()


if __name__ == "__main__":  # pragma: no cover
    from bridge.cli import main
    sys.exit(main())
