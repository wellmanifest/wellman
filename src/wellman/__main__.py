"""Execution entrypoint for `python -m wellman`."""

import sys
from wellman.cli import main

if __name__ == "__main__":
    sys.exit(main())
