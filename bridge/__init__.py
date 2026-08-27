"""brymen-tc-bridge — BM78xBT (BLE) -> TestController SingleValue bridge.

Public API:

- ``Emitter`` / ``FUNCTION_TO_MODE``: format parsed Brymen readings as
  TestController SingleValue lines.
- ``TcpLineServer``: TCP server the bridge writes lines to (TestController
  connects here with the Socket interface).
- ``run_bridge``: connect to the meter and stream lines until cancelled.
"""

import importlib.metadata

from .bridge import run_bridge
from .emitter import FUNCTION_TO_MODE, Emitter
from .transports import TcpLineServer

try:
    # Single source of truth: the installed distribution version (pyproject).
    # Falls back to a literal only when the package isn't installed (e.g. a
    # bare source checkout), so the two can never silently drift.
    __version__ = importlib.metadata.version("brymenble-tc-bridge")
except importlib.metadata.PackageNotFoundError:  # pragma: no cover - source checkout
    __version__ = "0.1.1"

__all__ = ["Emitter", "FUNCTION_TO_MODE", "TcpLineServer", "run_bridge"]
