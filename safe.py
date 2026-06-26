#!/usr/bin/env python3
"""safe.py - entrypoint for safe_tool modular CLI."""

from __future__ import annotations

import sys

from safe_tool.cli import main


if __name__ == "__main__":
    sys.exit(main())
