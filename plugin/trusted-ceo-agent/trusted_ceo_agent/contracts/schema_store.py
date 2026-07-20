from __future__ import annotations

from decimal import Decimal
from pathlib import Path, PurePosixPath
import threading
from typing import Any, Iterator
from urllib.parse import urldefrag, urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.errors import ContractError


class _BundleState:
    def __init__(self, available: set[str]) -> None:
        self.available = frozenset(available)
        self.schemas: dict[str, dict[str, Any]] = {}
        self.loading: set[str] = set()
        self.validators: dict[str, Draft202012Validator] = {}
        self.format_checker = FormatChecker()
        self.lock = threading.RLock()


_BUNDLE_CACHE_LOCK = threading.Lock()
_BUNDLE_CACHE: dict[
    str,
    tuple[tuple[tuple[str, int, int, int], ...], _BundleState],
] = {}


def _bundle_state(root: Path, paths: list[Path]) -> _BundleState:
    """Reuse parsed immutable schemas until a file-system fingerprint changes."""

    fingerprint_items: list[tuple[str, int, int, int]] = []
    for path in paths:
        details = path.stat()
        fingerprint_items.append(
            (path.name, details.st_size, details.st_mtime_ns, details.st_ctime_ns)
        )
    fingerprint = tuple(fingerprint_items)
    key = str(root)
    with _BUNDLE_CACHE_LOCK:
        cached = _BUNDLE_CACHE.get(key)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]
        state = _BundleState({path.name for path in paths})
        _BUNDLE_CACHE[key] = (fingerprint, state)
        return state


def _schema_numbers(value: Any) -> Any:
    """Convert integer-valued Decimal schema keywords to Python integers."""
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    if isinstance(value, dict):
        return {key: _schema_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_schema_numbers(child) for child in value]
    return value


def _walk_refs(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref":
                if not isinstance(child, str):
                    raise ContractError("schema $ref must be a string")
                yield child
            yield from _walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_refs(child)


def _local_ref_name(ref: str, available: set[str]) -> str | None:
    if ref.startswith("#"):
        return None
    document, _ = urldefrag(ref)
    parsed = urlsplit(document)
    if parsed.scheme or parsed.netloc or document.startswith(("/", chr(92))):
        raise ContractError(f"non-local schema reference is forbidden: {ref}")
    path = PurePosixPath(document.replace(chr(92), "/"))
    if not document or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ContractError(f"schema reference escapes bundle: {ref}")
    if len(path.parts) != 1 or path.name not in available:
        raise ContractError(f"unknown schema reference: {ref}")
    return path.name


class SchemaStore:
    """Lazily loads the immutable local Draft 2020-12 schema bundle."""

    def __init__(self, schema_root: Path | None = None) -> None:
        self.root = (schema_root or Path(__file__).resolve().parents[2] / "schemas").resolve()
        if not self.root.is_dir():
            raise ContractError(f"schema root does not exist: {self.root}")
        paths = sorted(self.root.glob("*.schema.json"))
        if not paths:
            raise ContractError("schema bundle is empty")
        self._state = _bundle_state(self.root, paths)
        self._available = self._state.available
        self._schemas = self._state.schemas
        self._loading = self._state.loading
        self._format_checker = self._state.format_checker

    def _load_recursive(self, name: str) -> dict[str, Any]:
        with self._state.lock:
            if name in self._schemas:
                return self._schemas[name]
            if name not in self._available:
                raise ContractError(f"unknown schema: {name}")
            if name in self._loading:
                raise ContractError(f"cyclic schema reference: {name}")
            self._loading.add(name)
            try:
                path = self.root / name
                try:
                    value = _schema_numbers(strict_loads(path.read_bytes()))
                except (OSError, UnicodeError, ValueError) as error:
                    raise ContractError(f"invalid schema JSON: {name}: {error}") from error
                if not isinstance(value, dict):
                    raise ContractError(f"schema root must be an object: {name}")
                dependencies: list[str] = []
                for ref in _walk_refs(value):
                    dependency = _local_ref_name(ref, set(self._available))
                    if dependency is not None:
                        dependencies.append(dependency)
                try:
                    Draft202012Validator.check_schema(value)
                except SchemaError as error:
                    raise ContractError(f"invalid schema: {name}: {error.message}") from error
                self._schemas[name] = value
                for dependency in sorted(set(dependencies)):
                    self._load_recursive(dependency)
                return value
            finally:
                self._loading.discard(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._available))

    def load(self, name: str) -> dict[str, Any]:
        return self._load_recursive(name)

    def validate(self, name: str, value: Any) -> None:
        schema = self.load(name)
        with self._state.lock:
            validator = self._state.validators.get(name)
            if validator is None:
                registry = Registry()
                for resource_name, resource_schema in self._schemas.items():
                    registry = registry.with_resource(
                        resource_name, Resource.from_contents(resource_schema)
                    )
                validator = Draft202012Validator(
                    schema,
                    registry=registry,
                    format_checker=self._format_checker,
                )
                self._state.validators[name] = validator
        errors = sorted(validator.iter_errors(value), key=lambda item: tuple(str(part) for part in item.absolute_path))
        if errors:
            error = errors[0]
            location = "/" + "/".join(str(part) for part in error.absolute_path)
            raise ContractError(f"{name}{location}: {error.message}") from error

    def validate_json(self, name: str, payload: str | bytes) -> Any:
        try:
            value = _schema_numbers(strict_loads(payload))
        except (UnicodeError, ValueError) as error:
            raise ContractError(f"invalid strict JSON: {error}") from error
        self.validate(name, value)
        return value
