"""Format Brymen readings as TestController "SingleValue" driver lines.

TestController's SingleValue driver (see the "Non SCPI device drivers"
documentation) expects a device to emit one ASCII line per reading::

    <value> <unit>             e.g. "607.80 V", "45.30 mV", "10.25 kOhm"
    <mode> <value> <unit>      e.g. "DCV 607.80 V"   (multi-mode variant)

The value is a plain decimal number; the unit (with SI prefix) follows as
text. The optional leading ``<mode>`` is a token of letters that
TestController uses to select a ``#value`` row — the exact letters it derives
from the line must be verified in TestController's debug mode (see the
README); the tokens here match the selectors in
``testcontroller/BM78xBT.txt``.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from brymen import ReadingPacket, StreamFrame

# Unit symbol -> ASCII-safe text. TestController reads lines as ISO-8859-1,
# where the Greek "Ω" is not representable (would become "?"). "°C"/"°F" are
# fine (U+00B0 is in ISO-8859-1).
UNIT_ASCII = {"Ω": "Ohm"}

# Metric prefix symbol -> ASCII-safe text. "µ" (U+00B5) is in ISO-8859-1, but
# "u" avoids any confusion with milli and is a safe default.
PREFIX_ASCII = {"µ": "u"}

# Metric prefix symbol -> power of ten, used to scale a reading to base units
# (TestController's "si" #value format then re-applies the prefix for display).
PREFIX_POWER = {"n": -9, "u": -6, "µ": -6, "m": -3, "": 0, "k": 3, "M": 6, "G": 9}

# Canonical SDK function name (constants.FUNCTION_NAMES) -> SingleValue mode
# token (LETTERS ONLY — TestController absorbs any digit in the leading token
# into the value, so tokens like "T1" would corrupt the reading). These tokens
# match the selectors in testcontroller/BM78xBT.txt.
FUNCTION_TO_MODE: Dict[str, str] = {
    "LoZ-ACV": "LoZACV",
    "LoZ-DCV": "LoZDCV",
    "AUTO": "AUTO",
    "ACV": "ACV",
    "DCV": "DCV",
    "DC+ACV": "DCACV",
    "Hz of VFD-ACV": "VFDHz",
    "VFD-ACV": "VFDAC",
    "ACmV": "ACmV",
    "DCmV": "DCmV",
    "DC+ACmV": "DCACmV",
    "ACµA": "ACuA",
    "DCµA": "DCuA",
    "DC+ACµA": "DCACuA",
    "ACmA": "ACmA",
    "DCmA": "DCmA",
    "DC+ACmA": "DCACmA",
    "%4~20mA": "PCT",
    "ACA": "ACA",
    "DCA": "DCA",
    "DC+ACA": "DCACA",
    "T1": "TC",
    "T2": "TD",
    "T1-T2": "TCD",
    "Resistance": "RES",
    "Capacitance": "CAP",
    "Continuity": "CONT",
    "Diode": "DIODE",
    "nS Conductance": "COND",
    "Duty Cycle (%)": "DUTY",
    "Logic-Hz": "LOGIC",
    "EF-Lo": "EFLO",
    "EF-Hi": "EFHI",
    "Hz of Line Signal": "LINE",
}

# Text emitted for an overload reading. SingleValue maps this via #valueText.
OVERLOAD_TEXT = "OL"

# Text emitted during a link-up data gap (function/range switch). It is a
# dedicated "?" token (a non-numeric #valueText value) so TestController keeps
# the connection and shows its "?" placeholder. It deliberately does NOT
# collide with a real meter ASCII output (the meter's map is Auto/InEr/dashes/
# EF-H/EF-L), hence "?" plus a matching "#valueText ? ?" row in both .txt defs.
GAP_TEXT = "?"

# Display accommodation (NOT protocol behavior): the meter's LCD shows "----"
# (4 dashes) for a temperature overload even though the protocol only sends the
# OL flag (real-meter capture cap-010 in the SDK fixtures). The SDK stays
# protocol-faithful ("OL"); the bridge mirrors the meter's actual display for
# T1/T2/T1-T2, and the defs have a matching "#valueText \"----\"" row.
TEMP_OVERLOAD_FUNCTIONS = ("T1", "T2", "T1-T2")
TEMP_OVERLOAD_TEXT = "----"


class Emitter:
    """Turn parsed Brymen frames into SingleValue lines for a consumer.

    ``line_format`` is a template with placeholders: ``{value}`` (the raw
    meter value at its displayed decimals), ``{si_value}`` (the value scaled
    to base units — pair with a ``si`` #value row so TestController re-applies
    the SI prefix), ``{prefix}`` (ASCII-safe prefix symbol), ``{unit}``
    (prefix + unit text) and ``{mode}`` (letters-only mode token).

    The default ``"{mode} {si_value}"`` is deterministic for TestController's
    SingleValue driver: the mode is exactly the leading letters, and there are
    no unit letters after the number to pollute it. Overload / ASCII states
    (``OL``, ``Auto``, ``InEr``, ...) are emitted as ``{mode} <token> `` — with
    a trailing space, never bare text: TestController's ``#valueText`` handler
    strips the token, rebuilds the mode from the remaining letters and reads
    one char past the token, so a bare / last-token ``OL`` drops the socket
    and a trailing unit pollutes the mode. The trailing space is preserved by
    TC's socket reader and leaves the mode clean.
    """

    def __init__(
        self,
        line_format: str = "{mode} {si_value}",
        function_modes: Optional[Dict[str, str]] = None,
        prefix_ascii: bool = True,
        unit_ascii: bool = True,
    ) -> None:
        self.line_format = line_format
        self._modes = dict(FUNCTION_TO_MODE)
        if function_modes:
            self._modes.update(function_modes)
        self.prefix_ascii = prefix_ascii
        self.unit_ascii = unit_ascii

    # -- public ----------------------------------------------------------

    def format_frame(self, frame: Optional[StreamFrame]) -> List[str]:
        """Return the SingleValue lines for a frame (usually one)."""
        lines: List[str] = []
        if frame is None:
            return lines
        for reading in frame.readings or ():
            if reading is None:
                continue
            line = self.format_reading(reading)
            if line:
                lines.append(line)
        return lines

    def format_reading(self, reading: ReadingPacket) -> Optional[str]:
        """Format one reading, or None if nothing sensible can be emitted."""
        value = self._value_text(reading)
        if value is None:
            return None
        if reading.is_overload or reading.is_ascii:
            # Overload / ASCII tokens ("OL", "Auto", "InEr", ...) are matched
            # by TestController's #valueText rows. TC's SingleValue valueText
            # handler strips the matched token, rebuilds the mode from the
            # REMAINING letters, and reads one char past the token — so the
            # token must never be the last thing on the line:
            #   * bare "OL"            -> substring past the end -> socket drop
            #   * "DCV OL V" (unit)    -> mode "DCVV" -> no #value row matches
            #   * "DCV OL " (trailing space) -> mode "DCV" -> matches  OK
            # The trailing space survives TC's socket reader (it does not trim
            # the line) and keeps the mode clean in single- and multi-mode.
            # The mode token is included only when the template uses it.
            mode = self._mode_text(reading)
            prefix = f"{mode} " if "{mode}" in self.line_format else ""
            return f"{prefix}{value} "
        ctx = {
            "mode": self._mode_text(reading),
            "value": value,
            "si_value": self._si_value_text(reading),
            "prefix": self._prefix_text(reading),
            "unit": self._unit_text(reading),
        }
        try:
            return self.line_format.format(**ctx)
        except (KeyError, ValueError, IndexError):
            # Malformed template -> fall back to the plain form.
            return f"{ctx['value']} {ctx['unit']}"

    def gap_line(self, reading: Optional[ReadingPacket] = None) -> str:
        """A keep-alive line for a data gap (e.g. a function/range switch).

        TestController's SingleValue socket reader closes the connection after
        ~1.5-2 s of silence, and the meter blanks its display during a switch,
        so the bridge would otherwise feed TC nothing and lose it. Sending the
        dedicated non-numeric ``#valueText`` token ``"?"`` makes TC show its "?"
        placeholder instead of a real reading. ``reading`` supplies the last
        known mode token so the multi-mode def still has a column to show the
        "?" in; pass None for a template without ``{mode}`` (no mode token).
        """
        mode = self._mode_text(reading) if reading is not None else None
        prefix = f"{mode} " if ("{mode}" in self.line_format and mode) else ""
        return f"{prefix}{GAP_TEXT} "

    # -- internals --------------------------------------------------------

    def _value_text(self, reading: ReadingPacket) -> Optional[str]:
        """The numeric/text value part of the line."""
        if reading.is_overload:
            # The meter's LCD shows "----" for a temperature overload; the
            # protocol only sends the OL flag, so this is a bridge-side display
            # accommodation (see TEMP_OVERLOAD_FUNCTIONS above).
            if reading.function_name in TEMP_OVERLOAD_FUNCTIONS:
                return TEMP_OVERLOAD_TEXT
            return OVERLOAD_TEXT
        if reading.is_ascii:
            return reading.ascii_text if reading.ascii_text else OVERLOAD_TEXT
        value = reading.value
        if value is None:
            return OVERLOAD_TEXT
        # mantissa is an integer scaled by 10**decimals, so formatting to the
        # meter's decimals reproduces the exact displayed digits.
        return f"{value:.{reading.decimals}f}"

    def _si_value_text(self, reading: ReadingPacket) -> str:
        """The value scaled to base units, e.g. 45.30 mV -> "0.04530".

        The meter reports mantissa in the prefixed unit (45.30 mV), and
        TestController's "si" #value format re-applies the SI prefix on
        display, so sending the base-unit number with a prefix-less unit row
        (e.g. ``#value DCmV V si DCmV``) shows "45.30m" correctly.
        """
        value = reading.value
        if value is None:
            return OVERLOAD_TEXT
        power = PREFIX_POWER.get(reading.prefix, 0)
        base = value * (10.0 ** power)
        decimals = max(0, reading.decimals - power)
        return f"{base:.{decimals}f}"

    def _prefix_text(self, reading: ReadingPacket) -> str:
        """ASCII-safe metric prefix symbol, e.g. "m", "u", "k", "" (none)."""
        prefix = reading.prefix or ""
        if self.prefix_ascii:
            prefix = PREFIX_ASCII.get(prefix, prefix)
        return prefix

    def _unit_base_text(self, reading: ReadingPacket) -> str:
        """Unit without prefix, ASCII-safe, e.g. "V", "A", "Ohm"."""
        unit = reading.unit or ""
        if self.unit_ascii:
            unit = UNIT_ASCII.get(unit, unit)
        return unit

    def _unit_text(self, reading: ReadingPacket) -> str:
        """Prefix + unit as ASCII text, e.g. "mV", "kOhm", "uA", "V" (for the
        ``{unit}`` placeholder used by the plain "{value} {unit}" form)."""
        return f"{self._prefix_text(reading)}{self._unit_base_text(reading)}"

    def _mode_text(self, reading: ReadingPacket) -> str:
        """Mode token for the line (letters only, ASCII-safe)."""
        token = self._modes.get(reading.function_name)
        if token is not None:
            return token
        # Fallback: letters from the canonical SDK function name.
        return "".join(ch for ch in reading.function_name if ch.isalpha())
