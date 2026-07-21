from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.service.contracts import UploadedFileSummary


def registry_upload_usage(
    registry: Sequence[Any],
) -> tuple[dict[str, str], dict[str, int]]:
    source_id_by_path: dict[str, str] = {}
    size_by_sha256: dict[str, int] = {}
    for item in registry:
        if not isinstance(item, Mapping):
            raise IntegrityError('source registry entry is invalid')
        source_id = item.get('source_id')
        digest = item.get('sha256')
        size = item.get('size_bytes')
        display_name = item.get('display_name')
        aliases = item.get('aliases', [])
        if (
            not isinstance(source_id, str)
            or not isinstance(digest, str)
            or re.fullmatch(r'[0-9a-f]{64}', digest) is None
            or isinstance(size, bool)
            or not isinstance(size, (int, Decimal))
            or size != int(size)
            or size < 0
            or not isinstance(display_name, str)
            or not isinstance(aliases, list)
        ):
            raise IntegrityError('source registry upload metadata is invalid')
        normalized_size = int(size)
        known_size = size_by_sha256.get(digest)
        if known_size is not None and known_size != normalized_size:
            raise IntegrityError('source registry digest size is ambiguous')
        size_by_sha256[digest] = normalized_size
        for logical_path in [display_name, *aliases]:
            if not isinstance(logical_path, str):
                raise IntegrityError('source registry logical path is invalid')
            claimed = source_id_by_path.get(logical_path)
            if claimed is not None and claimed != source_id:
                raise IntegrityError('source registry logical path is ambiguous')
            source_id_by_path[logical_path] = source_id
    return source_id_by_path, size_by_sha256


def uploaded_file_summaries(
    registry: Sequence[Any],
) -> list[UploadedFileSummary]:
    registry_upload_usage(registry)
    summaries: list[UploadedFileSummary] = []
    for item in registry:
        source_id = str(item['source_id'])
        media_type = str(item['media_type'])
        size_bytes = int(item['size_bytes'])
        logical_paths = [item['display_name'], *item.get('aliases', [])]
        for logical_path in logical_paths:
            collection_label = (
                logical_path.split('/', 1)[0]
                if '/' in logical_path
                else '개별 파일'
            )
            summaries.append(UploadedFileSummary(
                source_id=source_id,
                logical_path=logical_path,
                display_name=logical_path.rsplit('/', 1)[-1],
                media_type=media_type,
                size_bytes=size_bytes,
                collection_label=collection_label,
            ))
    return sorted(summaries, key=lambda item: item.logical_path)
