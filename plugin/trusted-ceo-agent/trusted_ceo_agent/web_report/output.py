from __future__ import annotations

import os
import secrets
from pathlib import Path

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.filesystem import ensure_within


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def publish_web_report_output(
    destination: Path,
    payload: bytes,
    *,
    workspace: Path,
    run_dir: Path,
    plugin_root: Path,
) -> Path:
    """Publish a new bundle once, outside mutable or sensitive runtime roots."""

    if not isinstance(payload, bytes):
        raise TypeError("web report output payload must be bytes")
    try:
        workspace_root = workspace.resolve(strict=True)
        registered_run = run_dir.resolve(strict=True)
        plugin = plugin_root.resolve(strict=True)
        parent = destination.parent.resolve(strict=True)
        safe_parent = ensure_within(workspace_root, parent)
    except (OSError, ValueError) as error:
        raise ContractError(
            "web report output parent must be a real directory inside the workspace"
        ) from error
    if not safe_parent.is_dir():
        raise ContractError("web report output parent must be a directory")

    candidate = safe_parent / destination.name
    if not destination.name or destination.name in {".", ".."}:
        raise ContractError("web report output file name is invalid")
    restricted = (
        registered_run,
        plugin,
        workspace_root / "logs",
        workspace_root / "web" / "var",
    )
    if any(_is_within(candidate, root) for root in restricted):
        raise ContractError("web report output is inside a restricted runtime root")
    if candidate.exists() or candidate.is_symlink():
        raise ContractError("web report output already exists")

    temporary = safe_parent / (
        f".{candidate.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, candidate)
        except FileExistsError as error:
            raise ContractError("web report output already exists") from error
        except OSError as error:
            raise ContractError("web report output could not be published") from error
        _fsync_directory(safe_parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return candidate
