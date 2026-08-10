"""Tie the Brymen SDK, the SingleValue emitter and a transport together."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from brymen import BrymenClient

from .emitter import Emitter
from .transports import TcpLineServer

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
    stale_timeout: float = 10.0,
    pause_cap: float = 60.0,
    sync_rtc: bool = False,
) -> None:
    """Connect to the meter and stream SingleValue lines to ``server``.

    Runs until cancelled. The meter is reconnected forever (it may power off
    mid-test). ``stale_timeout`` is how often a lack of data is checked;
    ``pause_cap`` bounds how long a BLE-link-up silence is tolerated before a
    reconnect is forced anyway (e.g. the link-state report lags behind a real
    power-off).
    """
    client = BrymenClient(mac, password, sync_rtc_on_connect=sync_rtc)
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

        silence_since: Optional[float] = None
        while True:
            try:
                frame = await client.wait_frame(timeout=stale_timeout)
            except RuntimeError:
                # Queue was torn down (reconnect in flight / not connected).
                silence_since = None
                await asyncio.sleep(1.0)
                await client.ensure_connected(retries=None, on_retry=_on_retry)
                continue

            if frame is not None:
                silence_since = None
                for line in emitter.format_frame(frame):
                    await server.send(line)
                continue

            # No frame for `stale_timeout`. A data gap alone is ambiguous:
            # the meter may be pausing (function switch / slow mode / HOLD)
            # or it may have powered off.
            if client.is_connected:
                # BLE link is still up -> the meter is alive but paused. Do
                # NOT reconnect (that was the spurious-timeout bug); just keep
                # waiting, bounded by `pause_cap` in case the link-state
                # report lags or the meter is stuck without streaming.
                if silence_since is None:
                    silence_since = time.monotonic()
                    log.info(
                        "no data for %.0fs but BLE link still up — "
                        "treating as a pause (not reconnecting)",
                        stale_timeout,
                    )
                elif time.monotonic() - silence_since >= pause_cap:
                    log.warning(
                        "no data for %.0fs with link up — forcing reconnect",
                        pause_cap,
                    )
                    silence_since = None
                    await client.ensure_connected(retries=None, on_retry=_on_retry)
                continue

            # BLE link dropped -> the meter powered off / went out of range.
            log.warning("BLE link lost — reconnecting")
            silence_since = None
            await client.ensure_connected(retries=None, on_retry=_on_retry)
    finally:
        await client.close()
        await server.close()
