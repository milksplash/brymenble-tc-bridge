"""Serve synthetic SingleValue lines over TCP — configure and test
TestController without a real meter or BLE.

It behaves exactly like the bridge from TestController's point of view (a
TCP server on ``--port``), but cycles through a fixed set of sample readings
instead of connecting to a meter::

    python tools/simulate_meter.py [--port 6000] [--rate 1.0]
    python tools/simulate_meter.py --format "{mode} {si_value}"
    python tools/simulate_meter.py --format "{value} {unit}"   # single-mode def
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
from bridge.emitter import PREFIX_POWER  # noqa: E402

# Sample readings as (mode, value, unit). TestController's SingleValue driver
# is fed one line per reading.
#
# Three small groups so it is easy to watch in TestController:
#   * numeric readings — multi-mode "{mode} {si_value}" keeps the mode token
#     exact (no unit letters to pollute it);
#   * overload ("OL")   — ALWAYS sent with a trailing space: TC's valueText
#     handler strips the token, rebuilds the mode from the remaining letters
#     and reads one char past the token. A bare / last-token "OL" drops the
#     socket; a trailing unit pollutes the multi-mode token ("DCV OL V" ->
#     mode "DCVV" -> no column); a single trailing space keeps the mode
#     clean ("DCV OL " -> mode "DCV") and survives TC's socket reader;
#   * ASCII text states — same trailing-space rule.
# A "0.000 V" probe after each group confirms the display recovered.
SAMPLES = [
    # Numeric readings
    ("DCV", "607.80", "V"),
    ("ACV", "230.45", "V"),
    ("DCmV", "45.30", "mV"),
    ("RES", "10.25", "kOhm"),
    ("DCA", "-1.234", "A"),
    ("DCmA", "3.456", "mA"),
    ("DCuA", "88.90", "uA"),
    ("DUTY", "50.00", "%"),
    ("CAP", "1.234", "uF"),
    ("TC", "25.60", "C"),  # T1 on the meter -> bridge mode token "TC"
    ("DCV", "0.000", "V"),  # recovery probe

    # Overload (never bare — trailing unit required)
    ("DCV", "OL", "V"),
    ("DCV", "-OL", "V"),
    ("RES", "OL", "Ohm"),
    ("DCV", "0.000", "V"),  # recovery probe

    # ASCII text states
    ("DCV", "Auto", "V"),
    ("DCV", "InEr", "V"),
    ("DCV", "0.000", "V"),  # recovery probe
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="0.0.0.0", help="listen address (default: all)")
    p.add_argument("--port", type=int, default=6000, help="TCP port (default: 6000)")
    p.add_argument("--rate", type=float, default=1.0, help="seconds between samples (default: 1.0)")
    p.add_argument(
        "--format",
        default="{mode} {si_value}",
        help='line template, same as the bridge (default: "{mode} {si_value}"; '
        'single-mode def: "{value} {unit}")',
    )
    p.add_argument(
        "--skip-bare",
        action="store_true",
        help="skip the bare-text samples (value=None, e.g. OL/Auto/InEr) that "
        "drop the TestController connection — use to isolate the numeric/multi-mode "
        "format without the connection-poisoning states",
    )
    return p


def _format_sample(template: str, mode: str, value, unit) -> str:
    if value is None:
        return mode  # bare text (OL / Auto / ...)
    # Overload / ASCII tokens ("OL", "-OL", "Auto", "InEr", "EF-H", ...) are
    # NOT numbers. TC's valueText handler strips the token, rebuilds the mode
    # from the REMAINING letters, and reads one char past the token — so the
    # token must not be the last thing on the line. A trailing unit pollutes
    # the multi-mode token ("DCV OL V" -> mode "DCVV" -> no column); a single
    # trailing space keeps the mode clean and is not stripped by TC's socket
    # reader. Include the mode only when the template uses it.
    if not _looks_numeric(value):
        prefix = f"{mode} " if "{mode}" in template else ""
        return f"{prefix}{value} "  # note: trailing space is intentional
    # Numeric: same placeholders as the real bridge (bridge/emitter.py) —
    # {mode}, {value}, {si_value}, {prefix}, {unit}.
    ctx = {
        "mode": mode,
        "value": value,
        "si_value": _si_value(value, unit),
        "prefix": _prefix(unit),
        "unit": unit,
    }
    try:
        return template.format(**ctx)
    except (KeyError, ValueError, IndexError):
        return f"{value} {unit}"


def _looks_numeric(value: str) -> bool:
    """True if value is a plain decimal number (not an OL/ASCII token)."""
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _split_prefix(unit: str):
    """Split a unit text like "kOhm" into (prefix, base): ("k", "Ohm")."""
    for p in PREFIX_POWER:
        if p and unit.startswith(p):
            return p, unit[len(p):]
    return "", unit


def _prefix(unit: str) -> str:
    """SI prefix of a unit text ("kOhm" -> "k", "V" -> "")."""
    return _split_prefix(unit)[0]


def _si_value(value: str, unit: str) -> str:
    """Value scaled to base units, like the bridge's {si_value}: 45.30 mV ->
    "0.04530", 10.25 kOhm -> "10250". TestController's "si" #value rows
    re-apply the prefix for display."""
    prefix, _ = _split_prefix(unit)
    power = PREFIX_POWER.get(prefix, 0)
    decimals = len(value.split(".", 1)[1]) if "." in value else 0
    scaled = float(value) * (10.0 ** power)
    return f"{scaled:.{max(0, decimals - power)}f}"


async def _amain(args: argparse.Namespace) -> int:
    samples = SAMPLES
    if args.skip_bare:
        samples = [s for s in SAMPLES if s[1] is not None]
        if not samples:
            samples = SAMPLES
    server = TcpLineServer(host=args.host, port=args.port)
    await server.start()
    print(
        f"simulated bridge listening on {args.host}:{server.bound_port} — "
        "connect TestController here; Ctrl+C to stop."
    )
    if args.skip_bare:
        print(f"note: skipping {len(SAMPLES) - len(samples)} bare-text sample(s)")
    i = 0
    try:
        while True:
            mode, value, unit = samples[i % len(samples)]
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
