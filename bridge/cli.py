"""Command-line entry point for the brymen-tc-bridge.

Examples::

    python -m bridge --mac 12:34:56:78:9A:BC
    python -m bridge                          # scan for the first meter
    python -m bridge --port 7000 --host 127.0.0.1
    python -m bridge --format "{mode} {value} {unit}"   # multi-mode
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from brymen import DEFAULT_PASSWORD, find_first_meter

from .bridge import run_bridge
from .emitter import Emitter
from .transports import TcpLineServer

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="brymen-tc-bridge",
        description=(
            "Bridge a Brymen BM78xBT multimeter (BLE) to TestController's "
            "SingleValue driver over a TCP socket."
        ),
    )
    p.add_argument(
        "mac",
        nargs="?",
        metavar="MAC",
        help="meter MAC (XX:XX:XX:XX:XX:XX); if omitted, the first meter "
        "found by scanning is used",
    )
    p.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help="4-digit connection password (default: 0000)",
    )
    p.add_argument(
        "--host",
        default="0.0.0.0",
        help="address to listen on (default: all interfaces; use 127.0.0.1 "
        "to restrict to this machine)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=6000,
        help="TCP port TestController connects to (default: 6000)",
    )
    p.add_argument(
        "--format",
        default="{mode} {si_value}",
        help='SingleValue line template. Default: "{mode} {si_value}" '
        '(deterministic mode + base-unit value, matches '
        'BM78xBT-MultiMode.txt). Placeholders: {mode} {si_value} {value} '
        '{prefix} {unit}. Plain form (BM78xBT.txt): "{value} {unit}"',
    )
    p.add_argument(
        "--sync-rtc",
        action="store_true",
        help="sync the meter's RTC to the host clock on (re)connect",
    )
    p.add_argument(
        "--stale",
        type=float,
        default=10.0,
        help="seconds without a frame before checking link state "
        "(default: 10)",
    )
    p.add_argument(
        "--pause-cap",
        type=float,
        default=60.0,
        help="seconds of BLE-link-up silence before forcing a reconnect "
        "anyway. A function-switch pause keeps the link up and won't trigger "
        "a reconnect; this bounds the worst case (default: 60)",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="increase log verbosity (repeat for debug)",
    )
    return p


async def _amain(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format=LOG_FORMAT
    )

    # Open the socket FIRST so TestController can connect even while we wait
    # for the meter (it may be powered off / out of range / mid-reconnect).
    server = TcpLineServer(host=args.host, port=args.port)
    await server.start()
    print(
        f"Listening on {args.host}:{server.bound_port} — point TestController "
        f"at #port {server.bound_port}",
        file=sys.stderr,
    )

    mac = args.mac
    if mac is None:
        print("Scanning for a BM78xBT meter... (retrying until one is found)",
              file=sys.stderr)
        meter = await find_first_meter(
            retry_interval=5.0,
            on_retry=lambda attempt: print(
                f"  (attempt {attempt}: no meter in range yet — retrying in 5s...)",
                file=sys.stderr,
            ),
        )
        mac = meter.address
        print(f"Using {meter.name or 'BM78xBT'} at {mac}")

    emitter = Emitter(line_format=args.format)

    await run_bridge(
        mac=mac,
        password=args.password,
        server=server,
        emitter=emitter,
        stale_timeout=args.stale,
        pause_cap=args.pause_cap,
        sync_rtc=args.sync_rtc,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        print("\nbridge stopped.")
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
