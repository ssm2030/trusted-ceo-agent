from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ContentItem:
    type: str
    text: str | None = None
    refusal: str | None = None


@dataclass(frozen=True, slots=True)
class OutputItem:
    type: str
    content: tuple[ContentItem, ...]


@dataclass(frozen=True, slots=True)
class FakeResponse:
    status: str
    output: tuple[OutputItem, ...]
    incomplete_details: dict[str, Any] | None = None


class FakeAPIError(Exception):
    def __init__(self, status_code: int, message: str = "secret request body") -> None:
        self.status_code = status_code
        super().__init__(message)


class FakeResponsesTransport:
    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def completed(payload: str) -> FakeResponse:
    return FakeResponse(
        status="completed",
        output=(OutputItem("message", (ContentItem("output_text", text=payload),)),),
    )


def refusal(message: str = "safety refusal") -> FakeResponse:
    return FakeResponse(
        status="completed",
        output=(OutputItem("message", (ContentItem("refusal", refusal=message),)),),
    )


def incomplete() -> FakeResponse:
    return FakeResponse(
        status="incomplete",
        output=(),
        incomplete_details={"reason": "max_output_tokens"},
    )
