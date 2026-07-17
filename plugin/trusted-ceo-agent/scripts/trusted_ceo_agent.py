from __future__ import annotations

import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
plugin_path = str(PLUGIN_ROOT)
sys.path = [entry for entry in sys.path if entry != plugin_path]
sys.path.insert(0, plugin_path)

from trusted_ceo_agent.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
