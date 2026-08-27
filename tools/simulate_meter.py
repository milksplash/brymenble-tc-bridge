"""Serve synthetic SingleValue lines over TCP — configure and test
TestController without a real meter or BLE.

It behaves exactly like the bridge from TestController's point of view (a
TCP server on ``--port``), but serves a fixed set of sample readings instead
of connecting to a meter. Pick a sample with the keyboard and it is emitted
at ``--rate``; TestController sees the same lines the real bridge would send::

    python tools/simulate_meter.py [--port 6000] [--rate 1.0]
    python tools/simulate_meter.py --format "{mode} {si_value}"
    python tools/simulate_meter.py --format "{value} {unit}"   # custom template

Interactive controls (Windows console — works in VS Code / PowerShell):
    n / Right  -> next sample
    p / Left   -> previous sample
    <number> + Enter -> jump straight to a sample (menu is printed at start)
    c          -> toggle auto-cycle through every sample
    q          -> quit
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading

# Allow running from anywhere in the repo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.transports import TcpLineServer  # noqa: E402
from bridge.emitter import PREFIX_POWER  # noqa: E402

try:
    import msvcrt  # Windows-only raw console input
    HAS_KEYS = True
except ImportError:  # pragma: no cover - non-Windows fallback
    msvcrt = None
    HAS_KEYS = False

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
    ("TEMPONEC", "25.60", "C"),  # T1 in °C -> bridge mode token "TEMPONEC"
    ("TEMPONEF", "77.00", "F"),  # T1 in °F -> bridge mode token "TEMPONEF"

    # Overload (never bare — trailing unit required)
    ("DCV", "OL", "V"),
    ("DCV", "-OL", "V"),
    ("RES", "OL", "Ohm"),

    # ASCII text states
    ("DCV", "Auto", "V"),
    ("DCV", "InEr", "V"),
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
        'custom template: "{value} {unit}")',
    )
    p.add_argument(
        "--skip-bare",
        action="store_true",
        help="skip the bare-text samples (value=None, e.g. OL/Auto/InEr) that "
        "drop the TestController connection — use to isolate the numeric/multi-mode "
        "format without the connection-poisoning states",
    )
    p.add_argument(
        "--cycle",
        action="store_true",
        help="start with auto-cycle ON (advance through all samples at --rate)",
    )
    p.add_argument(
        "--start", type=int, default=1,
        help="1-based sample number to select at startup (default: 1)",
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


# --- Console presentation (mirrors overlay/demo.py) ----------------------------

def _sample_label(sample) -> str:
    """A readable menu label for a sample tuple (mode, value, unit)."""
    mode, value, unit = sample
    if value is None:
        return mode  # bare text
    if not _looks_numeric(value):
        return f"{mode} {value}"  # overload / ASCII token
    return f"{mode} {value} {unit}"  # numeric


def _menu_entry(i, samples, template) -> str:
    """Format one menu entry as 'N. label line' ('' if out of range).

    The emitted line is shown as a repr so the trailing space on overload /
    ASCII lines stays visible.
    """
    if i >= len(samples):
        return ""
    mode, value, unit = samples[i]
    line = _format_sample(template, mode, value, unit)
    return f"{i + 1:>3}. {_sample_label(samples[i]):<24} {line!r}"


def print_menu(samples, template) -> None:
    rule = "=" * 100
    print(rule)
    print(" BM78xBT bridge - simulated meter: samples served to TestController")
    print("-" * 100)
    print(" Controls: n/\u2192 next   p/\u2190 prev   <number>+Enter jump   c auto-cycle   q quit")
    print("-" * 100)
    # Two-column layout: items fill the left column top-to-bottom first, then
    # the right column (column-major), so the <number>+Enter jump still
    # matches the printed order.
    rows = (len(samples) + 1) // 2
    left_entries = [_menu_entry(row, samples, template) for row in range(rows)]
    left_width = max(len(e) for e in left_entries)
    for row in range(rows):
        left = left_entries[row]
        right = _menu_entry(rows + row, samples, template)
        if right:
            print(f" {left:<{left_width}}  |  {right}")
        else:
            print(f" {left}")
    print(rule)


def print_status(idx, total, label, line, auto_cycle) -> None:
    text = f"[{idx + 1:>2}/{total}] {label:<24} {line!r}"
    if auto_cycle:
        text += "  (auto-cycle ON)"
    print("\r" + text + "   ", end="", flush=True)


def _read_keys(loop, commands) -> None:
    """Background thread: read console keys and post commands to the loop."""
    digits = ""
    while True:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):                      # arrow / special keys
            ch = msvcrt.getwch()
            cmd = {"H": ("prev",), "P": ("next",),
                   "K": ("prev",), "M": ("next",)}.get(ch)
            digits = ""
        elif ch.isdigit():
            digits += ch                               # build the jump number
            cmd = None
        elif ch in ("\r", "\n"):                       # Enter commits jump
            cmd = ("jump", int(digits)) if digits else None
            digits = ""
        elif ch in ("n", "N"):
            cmd = ("next",); digits = ""
        elif ch in ("p", "P"):
            cmd = ("prev",); digits = ""
        elif ch in ("c", "C"):
            cmd = ("cycle",); digits = ""
        elif ch in ("q", "Q") or ch == "\x03":         # q or Ctrl+C
            cmd = ("quit",); digits = ""
        else:
            cmd = None; digits = ""
        if cmd:
            loop.call_soon_threadsafe(commands.put_nowait, cmd)


async def _amain(args: argparse.Namespace) -> int:
    samples = SAMPLES
    if args.skip_bare:
        # "Bare" = non-numeric text states (OL, Auto, InEr, ...) that drop the
        # TestController connection. No sample stores value=None, so filter on
        # whether the value looks numeric rather than `is not None`.
        samples = [s for s in SAMPLES if _looks_numeric(s[1])] or SAMPLES
    server = TcpLineServer(host=args.host, port=args.port)
    await server.start()
    print(
        f"simulated bridge listening on {args.host}:{server.bound_port} - "
        "connect TestController here; Ctrl+C to stop."
    )
    if args.skip_bare:
        print(f"note: skipping {len(SAMPLES) - len(samples)} bare-text sample(s)")
    auto_cycle = args.cycle
    print_menu(samples, args.format)
    if not HAS_KEYS:
        print("(no Windows console available - auto-cycling through all samples)")
        auto_cycle = True

    idx = max(0, min(args.start - 1, len(samples) - 1))
    commands: asyncio.Queue = asyncio.Queue()
    if HAS_KEYS:
        threading.Thread(
            target=_read_keys, args=(asyncio.get_running_loop(), commands),
            daemon=True,
        ).start()

    loop = asyncio.get_running_loop()
    current = -1
    next_send = loop.time()
    try:
        while True:
            nav = False
            while True:                                # drain pending commands
                try:
                    cmd = commands.get_nowait()
                except asyncio.QueueEmpty:
                    break
                kind = cmd[0]
                if kind == "next":
                    idx = (idx + 1) % len(samples); nav = True
                elif kind == "prev":
                    idx = (idx - 1) % len(samples); nav = True
                elif kind == "jump":
                    n = cmd[1]
                    if 1 <= n <= len(samples):
                        idx = n - 1; nav = True
                elif kind == "cycle":
                    auto_cycle = not auto_cycle
                    current = -1                       # force status refresh
                elif kind == "quit":
                    return
            if nav:
                next_send = loop.time()                # send the new pick now

            if idx != current:
                current = idx
                mode, value, unit = samples[idx]
                line = _format_sample(args.format, mode, value, unit)
                print_status(idx, len(samples), _sample_label(samples[idx]),
                             line, auto_cycle)

            if loop.time() >= next_send:
                mode, value, unit = samples[idx]
                line = _format_sample(args.format, mode, value, unit)
                await server.send(line)
                if auto_cycle:
                    idx = (idx + 1) % len(samples)
                next_send = loop.time() + args.rate
            await asyncio.sleep(0.05)
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
