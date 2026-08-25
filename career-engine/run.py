#!/usr/bin/env /home/nsl/miniconda3/envs/lnxenv/bin/python
"""Career Engine Entrypoint Wrapper."""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.cli import main

if __name__ == "__main__":
    main()
