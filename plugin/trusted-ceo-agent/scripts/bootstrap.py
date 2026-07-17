from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


class PreflightError(RuntimeError):
    """Raised when the prepared offline runtime cannot be trusted."""


REQUIRED_DISTRIBUTIONS = ("jsonschema", "openpyxl")


def analysis_command(plugin_root: Path, cli_args: Sequence[str]) -> list[str]:
    root = plugin_root.resolve()
    return [
        "uv",
        "run",
        "--project",
        str(root),
        "--frozen",
        "--offline",
        "--no-sync",
        "python",
        str(root / "scripts" / "trusted_ceo_agent.py"),
        *cli_args,
    ]


def _venv_python(plugin_root: Path) -> Path:
    name = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    return plugin_root / ".venv" / name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_project(plugin_root: Path) -> dict[str, object]:
    root = plugin_root.resolve()
    if sys.version_info[:2] != (3, 11):
        raise PreflightError("Python 3.11 is required")
    if shutil.which("uv") is None:
        raise PreflightError("uv is required")

    lock_path = root / "uv.lock"
    expected_path = root / "trust" / "runtime-lock.sha256"
    python_path = _venv_python(root)
    for path in (lock_path, expected_path, python_path):
        if not path.is_file():
            raise PreflightError(
                f"prepared runtime is missing {path.name}; run: "
                f"uv sync --project {root} --frozen"
            )

    actual_hash = _sha256(lock_path)
    expected_hash = expected_path.read_text(encoding="ascii").strip().lower()
    if actual_hash != expected_hash:
        raise PreflightError("uv.lock hash does not match trust/runtime-lock.sha256")

    probe = (
        "import importlib.metadata as m, json; "
        f"print(json.dumps({{n:m.version(n) for n in {REQUIRED_DISTRIBUTIONS!r}}}))"
    )
    completed = subprocess.run(
        [str(python_path), "-I", "-c", probe],
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise PreflightError("required dependencies are not importable in the prepared venv")

    return {
        "ok": True,
        "plugin_root": str(root),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "uv_lock_sha256": actual_hash,
        "dependencies": json.loads(completed.stdout),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trusted CEO Agent offline preflight")
    parser.add_argument("command", choices=("preflight",))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        result = check_project(root)
    except PreflightError as error:
        print(str(error), file=sys.stderr)
        return 3
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
