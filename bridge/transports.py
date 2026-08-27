"""Transports that carry emitted SingleValue lines to TestController.

The bridge acts as a TCP server: TestController connects to it using the
Socket interface (``#port <port>``) with the SingleValue driver, and the
bridge writes one ASCII line per reading, LF-terminated (SingleValue's
default ``#eol``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

log = logging.getLogger(__name__)

# Max outbound lines buffered per client before it is considered too slow and
# dropped. Bounds memory use and the slow-consumer case: a client that stops
# reading fills its queue and is dropped instead of stalling the whole event
# loop (see TcpLineServer.send).
_MAX_QUEUED_LINES = 1000


class _Client:
    """Per-client outbound state: a bounded queue plus a drain task.

    ``send()`` only enqueues (non-blocking); a background task drains the
    queue and writes to the socket. A slow reader fills the queue and is
    dropped, but never blocks the event loop or other clients.
    """

    def __init__(self, writer: asyncio.StreamWriter) -> None:
        self.writer = writer
        self.queue: "asyncio.Queue[bytes]" = asyncio.Queue(maxsize=_MAX_QUEUED_LINES)
        self.task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self.task = asyncio.create_task(self._drain_loop())

    async def _drain_loop(self) -> None:
        try:
            while True:
                data = await self.queue.get()
                self.writer.write(data)
                await self.writer.drain()
        except (ConnectionError, OSError, RuntimeError):
            pass
        except asyncio.CancelledError:
            raise
        finally:
            try:
                self.writer.close()
            except Exception:  # pragma: no cover - defensive
                pass


class TcpLineServer:
    """Accept TCP clients and broadcast lines (LF-terminated, ISO-8859-1).

    TestController (SingleValue driver, Socket interface) is the typical
    client. Multiple concurrent clients are supported (e.g. TestController
    plus a debug terminal / `tools/simulate_meter.py`).

    Each client gets its own bounded outbound queue drained by a background
    task, so a slow (stalled) reader can never block the event loop or the
    other clients — it just fills its queue and is dropped.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6000) -> None:
        self.host = host
        self.port = port
        self._server: Optional[asyncio.AbstractServer] = None
        self._clients: List[_Client] = []

    async def start(self) -> None:
        """Bind the listening socket. Idempotent: a second call is a no-op.

        The CLI opens the port before the meter is found (so TestController can
        connect immediately), while ``run_bridge()`` still calls ``start()``
        for programmatic use — the guard makes both safe.
        """
        if self._server is not None:
            return
        self._server = await asyncio.start_server(
            self._on_connect, self.host, self.port
        )

    @property
    def bound_port(self) -> int:
        """The actual bound port (resolves a ``port=0`` to the chosen one)."""
        if self._server is None or not self._server.sockets:
            return self.port
        return self._server.sockets[0].getsockname()[1]

    def client_count(self) -> int:
        return len(self._clients)

    async def send(self, line: str) -> None:
        """Enqueue one line to every connected client; drop slow/dead clients.

        This never blocks on a client's socket: each line is put on the
        client's bounded outbound queue (non-blocking). A client whose queue
        is full (a stalled reader) is dropped, so it can't stall the event
        loop or the other clients.
        """
        if not self._clients:
            return
        data = (line + "\n").encode("latin-1", "replace")
        for client in list(self._clients):
            try:
                client.queue.put_nowait(data)
            except asyncio.QueueFull:
                self._drop(client)

    async def close(self) -> None:
        for client in list(self._clients):
            self._drop(client)
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # -- internals --------------------------------------------------------

    async def _on_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        client = _Client(writer)
        self._clients.append(client)
        client.start()
        log.info("client connected: %s (%d connected)", peer, len(self._clients))
        try:
            while True:
                data = await reader.read(256)
                if not data:
                    break
                # TestController may probe identity on connect (SCPI-style
                # *idn?). Answer so a verification handshake doesn't time out;
                # the reply matches the #idString in the .txt files. Anything
                # else TC sends is ignored (the meter is read-only).
                text = data.decode("latin-1", "replace").strip()
                if text.upper().startswith("*IDN"):
                    writer.write(b"Brymen,BM78xBT,0,0\r\n")
                    await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            self._drop(client)
            log.info("client disconnected: %s (%d connected)", peer, len(self._clients))

    def _drop(self, client: _Client) -> None:
        if client in self._clients:
            self._clients.remove(client)
        if client.task is not None:
            client.task.cancel()
        try:
            client.writer.close()
        except Exception:  # pragma: no cover - defensive
            pass
