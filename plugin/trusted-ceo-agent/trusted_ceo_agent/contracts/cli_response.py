from __future__ import annotations

from typing import Any


def response(
    *,
    command: str,
    ok: bool,
    code: int,
    message: str,
    run_id: str | None = None,
    revision: int | None = None,
    state: str | None = None,
    data: Any = None,
) -> dict[str, Any]:
    return {
        "contract_version": "1.0.0",
        "ok": ok,
        "code": code,
        "command": command,
        "message": message,
        "run_id": run_id,
        "revision": revision,
        "state": state,
        "data": data,
    }

