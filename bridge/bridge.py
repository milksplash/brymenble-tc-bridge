"""Tie the Brymen SDK, the SingleValue emitter and a transport together."""

from __future__ import annotations

import logging

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
    power-off). Both map onto ``BrymenClient.read_stream()``, which owns the
    pause-vs-power-off decision.
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

        def _on_pause() -> None:
            log.info(
                "no data for %.0fs but BLE link still up — "
                "treating as a pause (not reconnecting)",
                stale_timeout,
            )

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
            no_data_timeout=stale_timeout,
            pause_cap=pause_cap,
            retries=None,
            on_retry=_on_retry,
            on_pause=_on_pause,
            on_lost=_on_lost,
            on_reconnected=_on_reconnected,
        ):
            for line in emitter.format_frame(frame):
                await server.send(line)
    finally:
        await client.close()
        await server.close()
