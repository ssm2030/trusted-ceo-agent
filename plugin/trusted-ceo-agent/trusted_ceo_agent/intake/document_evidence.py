from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError


MAX_CHUNK_CHARACTERS = 2_000
_HEADING = re.compile(r'^(#{1,6})[ \t]+(.+?)#*[ \t]*$')
_FENCE_OPEN = re.compile(r'^[ \t]{0,3}(`{3,}|~{3,})')


def normalize_markdown_blob(payload: bytes) -> str:
    if not isinstance(payload, bytes):
        raise ContractError('Markdown evidence blob must be bytes')
    try:
        decoded = payload.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ContractError('Markdown evidence blob must be UTF-8') from exc
    return _normalized_text(decoded)


def _normalized_text(value: str) -> str:
    if not isinstance(value, str):
        raise ContractError('Markdown evidence text must be a string')
    normalized = value.replace('\r\n', '\n').replace('\r', '\n')
    if normalized.startswith('\ufeff'):
        normalized = normalized[1:]
    if not normalized.strip():
        raise ContractError('Markdown evidence text must not be empty')
    if any(
        character not in {'\n', '\t'}
        and unicodedata.category(character) == 'Cc'
        for character in normalized
    ):
        raise ContractError('Markdown evidence text contains control characters')
    return normalized


def _is_fence_close(line: str, marker: tuple[str, int]) -> bool:
    character, minimum = marker
    candidate = line.rstrip('\n')
    return re.fullmatch(
        rf'[ \t]{{0,3}}{re.escape(character)}{{{minimum},}}[ \t]*',
        candidate,
    ) is not None


def _markdown_sections(normalized_text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    heading_stack: list[str] = []
    current: dict[str, Any] = {'heading_path': [], 'lines': []}
    fence: tuple[str, int] | None = None
    for line_number, line in enumerate(
        normalized_text.splitlines(keepends=True),
        start=1,
    ):
        candidate = line.rstrip('\n')
        if fence is not None:
            current['lines'].append((line_number, line))
            if _is_fence_close(line, fence):
                fence = None
            continue
        opening = _FENCE_OPEN.match(candidate)
        if opening is not None:
            marker = opening.group(1)
            fence = (marker[0], len(marker))
            current['lines'].append((line_number, line))
            continue
        heading = _HEADING.fullmatch(candidate)
        if heading is not None:
            if current['lines']:
                sections.append(current)
            level = len(heading.group(1))
            title = heading.group(2).strip()
            heading_stack = heading_stack[:level - 1]
            heading_stack.append(title)
            current = {
                'heading_path': list(heading_stack),
                'lines': [(line_number, line)],
            }
            continue
        current['lines'].append((line_number, line))
    if current['lines']:
        sections.append(current)
    return sections


def _bounded_markdown_chunks(
    sections: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for section in sections:
        heading_path = list(section['heading_path'])
        pending: list[tuple[int, str]] = []
        pending_characters = 0

        def flush_pending() -> None:
            nonlocal pending, pending_characters
            if not pending:
                return
            chunks.append(
                {
                    'heading_path': heading_path,
                    'line_start': pending[0][0],
                    'line_end': pending[-1][0],
                    'content': ''.join(line for _, line in pending),
                }
            )
            pending = []
            pending_characters = 0

        for line_number, line in section['lines']:
            if len(line) > MAX_CHUNK_CHARACTERS:
                flush_pending()
                for offset in range(0, len(line), MAX_CHUNK_CHARACTERS):
                    chunks.append(
                        {
                            'heading_path': heading_path,
                            'line_start': line_number,
                            'line_end': line_number,
                            'content': line[offset:offset + MAX_CHUNK_CHARACTERS],
                        }
                    )
                continue
            if pending and pending_characters + len(line) > MAX_CHUNK_CHARACTERS:
                flush_pending()
            pending.append((line_number, line))
            pending_characters += len(line)
        flush_pending()
    return chunks


def _source_fields(source: Mapping[str, Any]) -> tuple[str, str]:
    source_id = source.get('source_id')
    logical_path = source.get('display_name')
    if not isinstance(source_id, str) or re.fullmatch(
        r'source_[0-9a-f]{24}', source_id
    ) is None:
        raise ContractError('Markdown evidence Source has an invalid source_id')
    if not isinstance(logical_path, str) or not logical_path:
        raise ContractError('Markdown evidence Source has no logical path')
    return source_id, logical_path


def build_document_evidence(
    source: Mapping[str, Any],
    normalized_text: str,
) -> list[dict[str, Any]]:
    source_id, logical_path = _source_fields(source)
    markdown = _normalized_text(normalized_text)
    document_sha256 = hashlib.sha256(markdown.encode('utf-8')).hexdigest()
    chunks = _bounded_markdown_chunks(_markdown_sections(markdown))
    evidence: list[dict[str, Any]] = []
    for chunk_index, chunk in enumerate(chunks, start=1):
        content = chunk['content']
        content_sha256 = hashlib.sha256(content.encode('utf-8')).hexdigest()
        identifier_seed = {
            'source_id': source_id,
            'normalized_document_sha256': document_sha256,
            'chunk_index': chunk_index,
            'line_start': chunk['line_start'],
            'line_end': chunk['line_end'],
            'content_sha256': content_sha256,
        }
        body = {
            'document_evidence_id': make_id('document', identifier_seed),
            'source_id': source_id,
            'logical_path': logical_path,
            'chunk_index': chunk_index,
            'heading_path': chunk['heading_path'],
            'line_start': chunk['line_start'],
            'line_end': chunk['line_end'],
            'content': content,
            'content_sha256': content_sha256,
            'normalized_document_sha256': document_sha256,
            'locator_type': 'markdown_lines',
        }
        item = {
            **body,
            'integrity': {
                'payload_hash': hashlib.sha256(canonical_bytes(body)).hexdigest(),
            },
        }
        SchemaStore().validate('document-evidence.schema.json', item)
        evidence.append(item)
    return evidence


def validate_document_evidence_registry(
    source: Mapping[str, Any],
    normalized_text: str,
    registry: Sequence[Mapping[str, Any]],
) -> None:
    if isinstance(registry, (str, bytes)) or not isinstance(registry, Sequence):
        raise IntegrityError('Document Evidence registry must be a sequence')
    actual: list[dict[str, Any]] = []
    try:
        for item in registry:
            if not isinstance(item, Mapping):
                raise IntegrityError('Document Evidence item must be an object')
            materialized = dict(item)
            SchemaStore().validate('document-evidence.schema.json', materialized)
            actual.append(materialized)
        expected = build_document_evidence(source, normalized_text)
    except ContractError as exc:
        raise IntegrityError('Document Evidence registry is invalid') from exc
    if canonical_bytes(actual) != canonical_bytes(expected):
        raise IntegrityError('Document Evidence registry does not match its Source')
