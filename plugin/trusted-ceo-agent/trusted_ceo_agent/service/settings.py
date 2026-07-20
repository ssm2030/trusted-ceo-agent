from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_LOOPBACK_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765
_APPROVED_MODEL = "gpt-5.6"
_INTERNAL_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,256}$")


@dataclass(frozen=True, slots=True)
class ServiceSettings:
    host: str
    port: int
    service_root: Path
    internal_token: str = field(repr=False)
    openai_api_key: str | None = field(repr=False)
    model: str

    @property
    def ai_ready(self) -> bool:
        return bool(self.openai_api_key)

    @classmethod
    def from_environment(cls) -> ServiceSettings:
        host = os.environ.get("TRUSTED_CEO_SERVICE_HOST", _LOOPBACK_HOST)
        if host != _LOOPBACK_HOST:
            raise ValueError("TRUSTED_CEO_SERVICE_HOST must be 127.0.0.1")

        port_text = os.environ.get(
            "TRUSTED_CEO_SERVICE_PORT",
            str(_DEFAULT_PORT),
        )
        try:
            port = int(port_text)
        except ValueError as error:
            raise ValueError(
                "TRUSTED_CEO_SERVICE_PORT must be an integer",
            ) from error
        if not 1 <= port <= 65535:
            raise ValueError(
                "TRUSTED_CEO_SERVICE_PORT must be between 1 and 65535",
            )

        root_text = os.environ.get("TRUSTED_CEO_SERVICE_ROOT")
        if not root_text:
            raise ValueError("TRUSTED_CEO_SERVICE_ROOT is required")
        service_root = Path(root_text).expanduser().resolve()

        internal_token = os.environ.get("TRUSTED_CEO_INTERNAL_TOKEN", "")
        if _INTERNAL_TOKEN_PATTERN.fullmatch(internal_token) is None:
            raise ValueError(
                "TRUSTED_CEO_INTERNAL_TOKEN must be 32-256 base64url characters",
            )

        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if openai_api_key == "":
            openai_api_key = None
        elif openai_api_key is not None and any(
            character.isspace() for character in openai_api_key
        ):
            raise ValueError("OPENAI_API_KEY must not contain whitespace")

        return cls(
            host=host,
            port=port,
            service_root=service_root,
            internal_token=internal_token,
            openai_api_key=openai_api_key,
            model=_APPROVED_MODEL,
        )
