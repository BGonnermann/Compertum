"""Inspect the current workspace with the source version of the setup helper."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compertum.environment import main


if __name__ == "__main__":
    raise SystemExit(main())
