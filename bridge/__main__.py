"""Allow ``python -m bridge`` to run the CLI."""

import sys

from bridge.cli import main

if __name__ == "__main__":
    sys.exit(main())
