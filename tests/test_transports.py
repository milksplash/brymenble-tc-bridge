"""Tests for ``bridge/transports.py`` — the TCP line server.

Covers the SingleValue line framing, the *IDN? identity handshake, and the
client lifecycle, all over a real loopback TCP socket (no hardware).
"""
import asyncio

from bridge.transports import TcpLineServer


def run(coro):
    return asyncio.run(coro)


def test_send_line_to_client():
    async def _run():
        server = TcpLineServer(host="127.0.0.1", port=0)
        await server.start()
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", server.bound_port
            )
            try:
                assert server.client_count() == 1
                await server.send("DCV 607.80")
                line = await asyncio.wait_for(reader.readline(), timeout=2)
                assert line.decode("latin-1") == "DCV 607.80\n"
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await server.close()
    run(_run())


def test_idn_handshake():
    async def _run():
        server = TcpLineServer(host="127.0.0.1", port=0)
        await server.start()
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", server.bound_port
            )
            try:
                writer.write(b"*IDN?\r\n")
                await writer.drain()
                reply = await asyncio.wait_for(reader.readline(), timeout=2)
                assert reply.decode("latin-1") == "Brymen,BM78xBT,0,0\r\n"
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await server.close()
    run(_run())


def test_send_with_no_clients_is_noop():
    async def _run():
        server = TcpLineServer(host="127.0.0.1", port=0)
        await server.start()
        try:
            assert server.client_count() == 0
            await server.send("DCV 607.80")  # must not raise
        finally:
            await server.close()
    run(_run())


def test_slow_client_does_not_stall_send():
    # A client that never reads fills its bounded outbound queue; send() must
    # drop it rather than stall the whole event loop (the classic
    # slow-consumer foot-gun).
    async def _run():
        server = TcpLineServer(host="127.0.0.1", port=0)
        await server.start()
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", server.bound_port
            )
            try:
                assert server.client_count() == 1
                # The client never reads; send enough lines to overflow its
                # bounded queue. send() must return promptly (non-blocking)
                # and drop the stalled client.
                for _ in range(2000):
                    await asyncio.wait_for(server.send("DCV 607.80"), timeout=5)
                    if server.client_count() == 0:
                        break
                assert server.client_count() == 0
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await server.close()
    run(_run())


def test_start_is_idempotent():
    async def _run():
        server = TcpLineServer(host="127.0.0.1", port=0)
        await server.start()
        await server.start()  # second call is a no-op
        assert server._server is not None
        await server.close()
    run(_run())


def test_bound_port_resolves_zero():
    async def _run():
        server = TcpLineServer(host="127.0.0.1", port=0)
        await server.start()
        try:
            assert server.bound_port > 0
        finally:
            await server.close()
    run(_run())
