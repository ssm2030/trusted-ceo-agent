from __future__ import annotations

import copy
from pathlib import Path

from trusted_ceo_agent.canonical import strict_loads
from tests.unit.web_report.test_converter import (
    ROOT,
    RUN_ID,
    _build_finalized_run,
)


def finalized_files(root: Path) -> tuple[object, dict[str, bytes]]:
    store, _ = _build_finalized_run(root)
    snapshot = store.verify_revision(2)
    manifest = strict_loads((snapshot / "snapshot-manifest.json").read_bytes())
    files = {
        item["path"]: (snapshot / item["path"]).read_bytes()
        for item in manifest["files"]
    }
    return store, files


def copy_files(files: dict[str, bytes]) -> dict[str, bytes]:
    return copy.deepcopy(files)


__all__ = ["ROOT", "RUN_ID", "copy_files", "finalized_files"]
