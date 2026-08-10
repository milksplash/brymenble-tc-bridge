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


class TcpLineServer:
    """Accept TCP clients and broadcast lines (LF-terminated, ISO-8859-1).

    TestController (SingleValue driver, Socket interface) is the typical
    client. Multiple concurrent clients are supported (e.g. TestController
    plus a debug terminal / `tools/simulate_meter.py`).
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 6000) -> None:
        self.host = host
        self.port = port
        self._server: Optional[asyncio.AbstractServer] = None
        self._writers: List[asyncio.StreamWriter] = []

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
        return len(self._writers)

    async def send(self, line: str) -> None:
        """Write one line to every connected client; drop dead writers."""
        if not self._writers:
            return
        data = (line + "\n").encode("latin-1", "replace")
        for writer in list(self._writers):
            try:
                writer.write(data)
                await writer.drain()
            except (ConnectionError, OSError, RuntimeError):
                self._drop(writer)

    async def close(self) -> None:
        for writer in list(self._writers):
            try:
                writer.close()
            except Exception:  # pragma: no cover - defensive
                pass
        self._writers.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # -- internals --------------------------------------------------------

    async def _on_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        self._writers.append(writer)
        log.info("client connected: %s (%d connected)", peer, len(self._writers))
        try:
            while True:
                data = await reader.read(256)
                if not data:
                    break
                # TestController may probe identity on connect (SCPI-style
                # *idn?). Answer so a verification handshake doesn't time out;
                # the reply matches the #idString in the .def files. Anything
                # else TC sends is ignored (the meter is read-only).
                text = data.decode("latin-1", "replace").strip()
                if text.upper().startswith("*IDN"):
                    writer.write(b"Brymen,BM78xBT,0,0\r\n")
                    await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            self._drop(writer)
            log.info("client disconnected: %s (%d connected)", peer, len(self._writers))

    def _drop(self, writer: asyncio.StreamWriter) -> None:
        if writer in self._writers:
            self._writers.remove(writer)
        try:
            writer.close()
        except Exception:  # pragma: no cover - defensive
            pass
