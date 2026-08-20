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

from brymenble.parsers import ReadingPacket  # noqa: E402


@pytest.fixture
def make_reading():
    """Factory for a ReadingPacket with sane defaults; pass overrides."""
    def _make(**overrides):
        return ReadingPacket.example(**overrides)
    return _make
