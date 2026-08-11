"""Shared fixtures for the bridge test suite.

Adds the repo root to ``sys.path`` so ``import bridge`` works no matter where
pytest is launched from, and provides a factory for hand-built
``ReadingPacket`` objects — the emitter/transport logic is pure, so no BLE
hardware is needed to test it.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brymen.parsers import RtcTime  # noqa: E402


def _default_reading() -> dict:
    # A realistic numeric reading: 607.80 V on DCV (5-digit display).
    return {
        "function_name": "DCV",
        "unit": "V",
        "mantissa": 60780,
        "decimal_pos": 3,
        "prefix": "",
        "display_digit_count": 5,
        "logging_data_set_id": 0x000001,
        "device_reading_pk_id": 0x01,
        "device_type": 1,
        "status0": 0,
        "status1": 0,
        "rtc": RtcTime(2026, 8, 11, 12, 34, 56, 789),
        "is_crest": False,
        "is_relative": False,
        "is_held": False,
        "is_auto_range": False,
        "is_auto_hold": False,
        "is_ascii": False,
        "is_negative": False,
        "is_overload": False,
        "is_recording": False,
        "is_max": False,
        "is_min": False,
        "is_avg": False,
        "ascii_text": None,
        "crc_ok": True,
        "raw": b"",
    }


@pytest.fixture
def make_reading():
    """Factory for a ReadingPacket with sane defaults; pass overrides."""
    def _make(**overrides):
        fields = _default_reading()
        fields.update(overrides)
        from brymen.parsers import ReadingPacket
        return ReadingPacket(**fields)
    return _make
