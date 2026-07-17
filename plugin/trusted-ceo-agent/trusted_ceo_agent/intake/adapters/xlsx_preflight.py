from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from trusted_ceo_agent.errors import ContractError


@dataclass(frozen=True)
class XlsxLimits:
    max_entries: int = 10_000
    max_uncompressed_bytes: int = 100 * 1024 * 1024
    max_compression_ratio: float = 100.0


def preflight_xlsx(path: Path, limits: XlsxLimits | None = None) -> None:
    limits = limits or XlsxLimits()
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > limits.max_entries:
                raise ContractError("XLSX ZIP entry limit exceeded")
            total = 0
            for entry in entries:
                normalized_name = entry.filename.replace(chr(92), "/")
                member = PurePosixPath(normalized_name)
                if member.is_absolute() or ".." in member.parts:
                    raise ContractError(f"XLSX ZIP traversal is forbidden: {entry.filename}")
                lowered = normalized_name.casefold()
                if lowered.endswith("vbaproject.bin") or lowered.startswith("xl/externallinks/"):
                    raise ContractError(f"active or external XLSX content is forbidden: {entry.filename}")
                total += entry.file_size
                if total > limits.max_uncompressed_bytes:
                    raise ContractError("XLSX uncompressed size limit exceeded")
                if entry.file_size:
                    if entry.compress_size == 0:
                        raise ContractError("XLSX invalid zero compressed size")
                    if entry.file_size / entry.compress_size > limits.max_compression_ratio:
                        raise ContractError("XLSX compression ratio limit exceeded")
    except zipfile.BadZipFile as error:
        raise ContractError("invalid XLSX ZIP container") from error

