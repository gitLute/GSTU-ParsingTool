"""Entry point для ``python -m gstu_schedule_mcp``."""

from __future__ import annotations

import sys

from .server import main

if __name__ == "__main__":
    raise SystemExit(main())
