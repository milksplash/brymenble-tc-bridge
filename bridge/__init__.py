"""brymen-tc-bridge — BM78xBT (BLE) -> TestController SingleValue bridge.

Public API:

- ``Emitter`` / ``FUNCTION_TO_MODE``: format parsed Brymen readings as
  TestController SingleValue lines.
- ``TcpLineServer``: TCP server the bridge writes lines to (TestController
  connects here with the Socket interface).
- ``run_bridge``: connect to the meter and stream lines until cancelled.
"""

from .bridge import run_bridge
from .emitter import FUNCTION_TO_MODE, Emitter
from .transports import TcpLineServer

__version__ = "0.1.0"

__all__ = ["Emitter", "FUNCTION_TO_MODE", "TcpLineServer", "run_bridge"]
