"""Serve synthetic SingleValue lines over TCP — configure and test
TestController without a real meter or BLE.

It behaves exactly like the bridge from TestController's point of view (a
TCP server on ``--port``), but cycles through a fixed set of sample readings
instead of connecting to a meter::

    python tools/simulate_meter.py [--port 6000] [--rate 1.0]
    python tools/simulate_meter.py --format "{mode} {value} {unit}"
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

# Allow running from anywhere in the repo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.transports import TcpLineServer  # noqa: E402

# Sample readings as (mode, value, unit). When value is None the mode is
# emitted as bare text (overload / ASCII state), like the real bridge.
SAMPLES = [
    ("DCV", "607.80", "V"),
    ("DCV", "0.000", "V"),
    ("ACV", "230.45", "V"),
    ("DCmV", "45.30", "mV"),
    ("RES", "10.25", "kOhm"),
    ("RES", "0.325", "MOhm"),
    ("DCA", "-1.234", "A"),
    ("DCmA", "3.456", "mA"),
    ("DCuA", "88.90", "uA"),
    ("DUTY", "50.00", "%"),
    ("CAP", "1.234", "uF"),
    ("T1", "25.60", "C"),
    ("OL", None, None),
    ("Auto", None, None),
    ("InEr", None, None),
    ("DCV", "OL", "V"),
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="0.0.0.0", help="listen address (default: all)")
    p.add_argument("--port", type=int, default=6000, help="TCP port (default: 6000)")
    p.add_argument("--rate", type=float, default=1.0, help="seconds between samples (default: 1.0)")
    p.add_argument(
        "--format",
        default="{value} {unit}",
        help='line template (default: "{value} {unit}"; use "{mode} {value} {unit}" '
        "to test the multi-mode def)",
    )
    return p


def _format_sample(template: str, mode: str, value, unit) -> str:
    if value is None:
        return mode  # bare text (OL / Auto / ...)
    try:
        return template.format(mode=mode, value=value, unit=unit)
    except (KeyError, ValueError, IndexError):
        return f"{value} {unit}"


async def _amain(args: argparse.Namespace) -> int:
    server = TcpLineServer(host=args.host, port=args.port)
    await server.start()
    print(
        f"simulated bridge listening on {args.host}:{server.bound_port} — "
        "connect TestController here; Ctrl+C to stop."
    )
    i = 0
    try:
        while True:
            mode, value, unit = SAMPLES[i % len(SAMPLES)]
            i += 1
            line = _format_sample(args.format, mode, value, unit)
            print(f"> {line}")
            await server.send(line)
            await asyncio.sleep(args.rate)
    finally:
        await server.close()
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        print("\nsimulator stopped.")
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
