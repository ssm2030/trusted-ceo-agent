from __future__ import annotations

import json
import sys
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.cli_commands import dispatch
from trusted_ceo_agent.cli_parser import build_parser
from trusted_ceo_agent.contracts.cli_response import response
from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict


EXIT_CONTRACT = 3
EXIT_INTEGRITY = 4
EXIT_INTERNAL = 5
EXIT_CONFLICT = 6

def _emit(value: Mapping[str, Any]) -> None:
    payload = canonical_bytes(value).decode("utf-8") + "\n"
    sys.stdout.write(payload)
    sys.stdout.flush()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        code, value = dispatch(args)
    except RevisionConflict as error:
        code = EXIT_CONFLICT
        value = response(command=args.command, ok=False, code=code, message=str(error))
    except IntegrityError as error:
        code = EXIT_INTEGRITY
        value = response(command=args.command, ok=False, code=code, message=str(error))
    except (ContractError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        code = EXIT_CONTRACT
        value = response(command=args.command, ok=False, code=code, message=str(error))
    except Exception as error:  # pragma: no cover - defensive CLI boundary
        print(f"internal error: {error}", file=sys.stderr)
        code = EXIT_INTERNAL
        value = response(command=args.command, ok=False, code=code, message="internal error")
    _emit(value)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
