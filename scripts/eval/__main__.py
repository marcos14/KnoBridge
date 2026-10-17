"""``python -m eval``: see ``cli.py``."""

import sys

from eval.cli import main

if __name__ == "__main__":  # pragma: no cover - entry point, main() is tested directly
    sys.exit(main())
