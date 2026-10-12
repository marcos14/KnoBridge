"""``python -m synthetic_tickets``: see ``cli.py``."""

import sys

from synthetic_tickets.cli import main

if __name__ == "__main__":  # pragma: no cover - entry point, main() is tested directly
    sys.exit(main())
