from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any, Protocol, TextIO

_PLUGIN_ROOT = str(Path(__file__).resolve().parents[1])
if sys.path[0] != _PLUGIN_ROOT:
    sys.path.insert(0, _PLUGIN_ROOT)

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.service.contracts import RunSnapshot
from trusted_ceo_agent.service.questions import QuestionSnapshot
from trusted_ceo_agent.web_report.contracts import load_bundle_bytes


_FIXTURE_NAME = "company-diagnostic.json"
_FIXTURE_SHA256 = "e47d02bfa86a7ec76576670d874903540496ea3f54f3c38bdab7934d45f0a706"
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,256}$")
_RUN_ID = re.compile(r"^run_[A-Za-z0-9_-]{8,200}$")
_QUESTION_ID = re.compile(r"^questionrequest_[0-9a-f]{24}$")
_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
_MAX_STEPS = 128
_MAX_RUN_POLLS = 1_200
_MAX_QUESTION_POLLS = 1_200


class SmokeFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SmokeClient(Protocol):
    def health(self) -> Mapping[str, Any]: ...
    def create_run(self) -> Mapping[str, Any]: ...
    def upload_file(
        self,
        run_id: str,
        revision: int,
        fixture: Path,
    ) -> Mapping[str, Any]: ...
    def submit_hitl(
        self,
        run_id: str,
        snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...
    def continue_run(self, run_id: str, revision: int) -> Mapping[str, Any]: ...
    def retry_run(self, run_id: str, revision: int) -> Mapping[str, Any]: ...
    def resume_run(self, run_id: str, revision: int) -> Mapping[str, Any]: ...
    def get_run(self, run_id: str) -> Mapping[str, Any]: ...
    def get_report(self, run_id: str) -> Mapping[str, Any]: ...
    def start_question(self, run_id: str, revision: int) -> Mapping[str, Any]: ...
    def get_question(self, run_id: str, request_id: str) -> Mapping[str, Any]: ...
    def metrics(self) -> Mapping[str, int]: ...
    def delete_run(self, run_id: str, revision: int) -> None: ...


def _fixture(artifact_root: Path) -> Path:
    root = artifact_root.expanduser().resolve()
    candidate = (root / _FIXTURE_NAME).resolve()
    if not root.is_dir() or candidate.parent != root or not candidate.is_file():
        raise SmokeFailure("SMOKE_FIXTURE_REQUIRED")
    payload = candidate.read_bytes()
    if hashlib.sha256(payload).hexdigest() != _FIXTURE_SHA256:
        raise SmokeFailure("SMOKE_FIXTURE_REJECTED")
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SmokeFailure("SMOKE_FIXTURE_REJECTED") from None
    if not isinstance(value, list):
        raise SmokeFailure("SMOKE_FIXTURE_REJECTED")
    return candidate


def _validated_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return RunSnapshot.model_validate(value).model_dump(mode="json")
    except Exception:
        raise SmokeFailure("SERVICE_CONTRACT_INVALID") from None


def _validated_question(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        snapshot = QuestionSnapshot.model_validate(value)
        if snapshot.answer is not None:
            SchemaStore().validate("result-answer.schema.json", snapshot.answer)
        return snapshot.model_dump(mode="json")
    except Exception:
        raise SmokeFailure("SERVICE_CONTRACT_INVALID") from None


def _next_time(values: Iterator[float] | None) -> float:
    return time.monotonic() if values is None else float(next(values))


def _drive_run(
    client: SmokeClient,
    initial: Mapping[str, Any],
    *,
    pause: Callable[[float], None],
) -> tuple[dict[str, Any], int]:
    snapshot = _validated_snapshot(initial)
    run_id = snapshot["run_id"]
    stage_count = 0
    provider_polls = 0
    while stage_count < _MAX_STEPS:
        if snapshot["workflow_status"] == "finalized":
            if snapshot["pending_action"] != "terminal" or snapshot["error"] is not None:
                raise SmokeFailure("FINAL_STATE_INVALID")
            return snapshot, stage_count
        error = snapshot["error"]
        if error is not None:
            if error["retryable"] and "retry" in snapshot["allowed_actions"]:
                snapshot = _validated_snapshot(
                    client.retry_run(run_id, snapshot["revision"]),
                )
                stage_count += 1
                continue
            raise SmokeFailure(str(error["code"]))
        pending = snapshot["pending_action"]
        if pending != "provider_work" or "continue" in snapshot["allowed_actions"]:
            provider_polls = 0
        if pending == "human_response":
            card = snapshot["hitl_card"]
            if card is None or "approve" not in card["allowed_decisions"]:
                raise SmokeFailure("HITL_APPROVAL_UNAVAILABLE")
            snapshot = _validated_snapshot(client.submit_hitl(run_id, snapshot))
            stage_count += 1
        elif pending == "provider_work":
            if "continue" in snapshot["allowed_actions"]:
                snapshot = _validated_snapshot(
                    client.continue_run(run_id, snapshot["revision"]),
                )
                stage_count += 1
            else:
                provider_polls += 1
                if provider_polls > _MAX_RUN_POLLS:
                    raise SmokeFailure("SMOKE_PROVIDER_TIMEOUT")
                pause(0.25)
                snapshot = _validated_snapshot(client.get_run(run_id))
        elif pending == "retry" and "retry" in snapshot["allowed_actions"]:
            snapshot = _validated_snapshot(
                client.retry_run(run_id, snapshot["revision"]),
            )
            stage_count += 1
        elif pending == "resume" and "resume" in snapshot["allowed_actions"]:
            snapshot = _validated_snapshot(
                client.resume_run(run_id, snapshot["revision"]),
            )
            stage_count += 1
        else:
            raise SmokeFailure("SMOKE_WORKFLOW_BLOCKED")
    raise SmokeFailure("SMOKE_STAGE_LIMIT_EXCEEDED")


def _validate_report(report: Mapping[str, Any], run_id: str, revision: int) -> None:
    try:
        load_bundle_bytes(canonical_bytes(dict(report)))
        run = report["run"]
        if run["run_id"] != run_id or run["revision"] != revision:
            raise KeyError("report binding")
    except Exception:
        raise SmokeFailure("REPORT_VALIDATION_FAILED") from None


def _complete_question(
    client: SmokeClient,
    run_id: str,
    revision: int,
    *,
    pause: Callable[[float], None],
) -> None:
    snapshot = _validated_question(client.start_question(run_id, revision))
    for _poll in range(_MAX_QUESTION_POLLS):
        if snapshot["run_id"] != run_id or snapshot["revision"] != revision:
            raise SmokeFailure("SERVICE_CONTRACT_INVALID")
        state = snapshot["state"]
        if state == "completed":
            if snapshot["answer"] is None:
                raise SmokeFailure("QUESTION_VALIDATION_FAILED")
            return
        if state in {"failed", "cancelled", "scope_required"}:
            raise SmokeFailure(snapshot["error_code"] or "QUESTION_FAILED")
        pause(0.25)
        snapshot = _validated_question(
            client.get_question(run_id, snapshot["request_id"]),
        )
    raise SmokeFailure("QUESTION_TIMEOUT")


def execute_smoke(
    artifact_root: Path,
    client: SmokeClient,
    *,
    monotonic_values: Iterator[float] | None = None,
    pause: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    fixture = _fixture(Path(artifact_root))
    started = _next_time(monotonic_values)
    health = client.health()
    if (
        health.get("status") != "ok"
        or health.get("model") != "gpt-5.6"
        or not isinstance(health.get("ai_ready"), bool)
    ):
        raise SmokeFailure("SERVICE_CONTRACT_INVALID")
    if not health["ai_ready"]:
        raise SmokeFailure("AI_API_KEY_REQUIRED")

    created = _validated_snapshot(client.create_run())
    run_id = created["run_id"]
    uploaded = _validated_snapshot(
        client.upload_file(run_id, created["revision"], fixture),
    )
    if uploaded["run_id"] != run_id:
        raise SmokeFailure("SERVICE_CONTRACT_INVALID")
    final, stage_count = _drive_run(client, uploaded, pause=pause)
    report = client.get_report(run_id)
    _validate_report(report, run_id, final["revision"])
    _complete_question(
        client,
        run_id,
        final["revision"],
        pause=pause,
    )
    metrics = client.metrics()
    input_tokens = metrics.get("input_token_count", 0)
    output_tokens = metrics.get("output_token_count", 0)
    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or input_tokens < 0
        or isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
        or output_tokens < 0
    ):
        raise SmokeFailure("SERVICE_CONTRACT_INVALID")
    client.delete_run(run_id, final["revision"])
    elapsed = max(0.0, _next_time(monotonic_values) - started)
    return {
        "contract_valid": True,
        "stage_count": stage_count,
        "elapsed_seconds": elapsed,
        "input_token_count": input_tokens,
        "output_token_count": output_tokens,
        "final_validation": "passed",
    }


def write_summary(summary: Mapping[str, Any], stream: TextIO) -> None:
    lines = (
        f"contract_valid={'true' if summary['contract_valid'] else 'false'}",
        f"stage_count={summary['stage_count']}",
        f"elapsed_seconds={float(summary['elapsed_seconds']):.3f}",
        f"input_token_count={summary['input_token_count']}",
        f"output_token_count={summary['output_token_count']}",
        f"final_validation={summary['final_validation']}",
    )
    stream.write("\n".join(lines) + "\n")


class HttpSmokeClient:
    def __init__(self, service_url: str, internal_token: str) -> None:
        parsed = urllib.parse.urlsplit(service_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise SmokeFailure("SERVICE_URL_REJECTED")
        if _TOKEN.fullmatch(internal_token) is None:
            raise SmokeFailure("INTERNAL_TOKEN_REJECTED")
        self._base_url = f"http://127.0.0.1:{parsed.port}"
        self._token = internal_token
        self._input_tokens = 0
        self._output_tokens = 0
        self._baseline_input_tokens = 0
        self._baseline_output_tokens = 0

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        expected_status: int = 200,
    ) -> Any:
        if not path.startswith("/") or ".." in path or "://" in path:
            raise SmokeFailure("SERVICE_URL_REJECTED")
        request_headers = {
            "Accept": "application/json",
            "X-Trusted-Ceo-Internal-Token": self._token,
            **dict(headers or {}),
        }
        if content_type is not None:
            request_headers["Content-Type"] = content_type
        request = urllib.request.Request(
            self._base_url + path,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                status = response.status
                self._record_metrics(response.headers)
                payload = response.read(_MAX_RESPONSE_BYTES + 1)
                final_url = response.geturl()
                response_type = response.headers.get_content_type()
        except urllib.error.HTTPError as error:
            payload = error.read(_MAX_RESPONSE_BYTES + 1)
            code = "SERVICE_REQUEST_FAILED"
            try:
                value = json.loads(payload.decode("utf-8", errors="strict"))
                if isinstance(value, dict) and isinstance(value.get("code"), str):
                    code = value["code"]
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            raise SmokeFailure(code) from None
        except (OSError, TimeoutError, urllib.error.URLError):
            raise SmokeFailure("SERVICE_UNAVAILABLE") from None
        if final_url != self._base_url + path or status != expected_status:
            raise SmokeFailure("SERVICE_CONTRACT_INVALID")
        if len(payload) > _MAX_RESPONSE_BYTES:
            raise SmokeFailure("SERVICE_RESPONSE_TOO_LARGE")
        if expected_status == 204:
            if payload:
                raise SmokeFailure("SERVICE_CONTRACT_INVALID")
            return None
        if response_type != "application/json":
            raise SmokeFailure("SERVICE_CONTRACT_INVALID")
        try:
            value = json.loads(payload.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise SmokeFailure("SERVICE_CONTRACT_INVALID") from None
        if not isinstance(value, dict):
            raise SmokeFailure("SERVICE_CONTRACT_INVALID")
        return value

    def _record_metrics(self, headers: Any) -> None:
        for name, attribute in (
            ("X-Trusted-Ceo-Input-Tokens", "_input_tokens"),
            ("X-Trusted-Ceo-Output-Tokens", "_output_tokens"),
        ):
            raw = headers.get(name)
            if raw is None:
                continue
            try:
                count = int(raw)
            except ValueError:
                raise SmokeFailure("SERVICE_CONTRACT_INVALID") from None
            if count < 0:
                raise SmokeFailure("SERVICE_CONTRACT_INVALID")
            setattr(self, attribute, count)

    def _json(
        self,
        method: str,
        path: str,
        value: Mapping[str, Any],
        *,
        expected_status: int = 200,
    ) -> Any:
        body = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._request(
            method,
            path,
            body=body,
            content_type="application/json",
            expected_status=expected_status,
        )

    @staticmethod
    def _key(label: str) -> str:
        return f"{label}_{secrets.token_urlsafe(24)}"

    @staticmethod
    def _run_path(run_id: str) -> str:
        if _RUN_ID.fullmatch(run_id) is None:
            raise SmokeFailure("SERVICE_CONTRACT_INVALID")
        return f"/v1/runs/{urllib.parse.quote(run_id, safe='')}"

    def health(self) -> Mapping[str, Any]:
        value = self._request("GET", "/health")
        self._baseline_input_tokens = self._input_tokens
        self._baseline_output_tokens = self._output_tokens
        return value

    def create_run(self) -> Mapping[str, Any]:
        return self._json("POST", "/v1/runs", {
            "expected_revision": 0,
            "idempotency_key": self._key("smoke_create"),
        })

    def upload_file(
        self,
        run_id: str,
        revision: int,
        fixture: Path,
    ) -> Mapping[str, Any]:
        boundary = "trusted-ceo-smoke-" + secrets.token_hex(16)
        content_type = mimetypes.guess_type(fixture.name)[0] or "application/octet-stream"
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"expected_revision\"\r\n\r\n{revision}\r\n".encode("ascii"),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"idempotency_key\"\r\n\r\n{self._key('smoke_upload')}\r\n".encode("ascii"),
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{_FIXTURE_NAME}\"\r\n"
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("ascii"),
            fixture.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode("ascii"),
        ]
        return self._request(
            "POST",
            self._run_path(run_id) + "/files",
            body=b"".join(parts),
            content_type=f"multipart/form-data; boundary={boundary}",
        )

    def submit_hitl(
        self,
        run_id: str,
        snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any]:

        fingerprint = hashlib.sha256(b"trusted-ceo-live-smoke").hexdigest()
        path = self._run_path(run_id) + "/human-responses"
        body = {
            "expected_revision": snapshot["revision"],
            "idempotency_key": self._key("smoke_hitl"),
            "decision": "approve",
            "edits": {},
            "rationale": None,
        }
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        return self._request(
            "POST",
            path,
            body=encoded,
            content_type="application/json",
            headers={"X-Trusted-Ceo-Browser-Fingerprint": fingerprint},
        )

    def _action(self, run_id: str, revision: int, action: str) -> Mapping[str, Any]:
        return self._json(
            "POST",
            self._run_path(run_id) + f"/actions/{action}",
            {
                "expected_revision": revision,
                "idempotency_key": self._key(f"smoke_{action}"),
            },
        )

    def continue_run(self, run_id: str, revision: int) -> Mapping[str, Any]:
        return self._action(run_id, revision, "continue")

    def retry_run(self, run_id: str, revision: int) -> Mapping[str, Any]:
        return self._action(run_id, revision, "retry")

    def resume_run(self, run_id: str, revision: int) -> Mapping[str, Any]:
        return self._action(run_id, revision, "resume")

    def get_run(self, run_id: str) -> Mapping[str, Any]:
        return self._request("GET", self._run_path(run_id))

    def get_report(self, run_id: str) -> Mapping[str, Any]:
        value = self._request("GET", self._run_path(run_id) + "/report")
        bundle = value.get("bundle")
        eligibility = value.get("eligibility")
        if not isinstance(bundle, Mapping) or not isinstance(eligibility, Mapping):
            raise SmokeFailure("SERVICE_CONTRACT_INVALID")
        return bundle

    def start_question(self, run_id: str, revision: int) -> Mapping[str, Any]:
        return self._json(
            "POST",
            self._run_path(run_id) + "/questions",
            {
                "expected_revision": revision,
                "idempotency_key": self._key("smoke_question"),
                "question": "현재 실행본의 검증된 범위에서 핵심 결론을 알려주세요.",
                "scope_kind": "run",
                "scope_instance_id": "run",
                "privacy_classification": "poc_deidentified",
            },
            expected_status=202,
        )

    def get_question(self, run_id: str, request_id: str) -> Mapping[str, Any]:
        if _QUESTION_ID.fullmatch(request_id) is None:
            raise SmokeFailure("SERVICE_CONTRACT_INVALID")
        return self._request(
            "GET",
            self._run_path(run_id) + "/questions/" + urllib.parse.quote(request_id, safe=""),
        )

    def metrics(self) -> Mapping[str, int]:
        return {
            "input_token_count": max(
                0, self._input_tokens - self._baseline_input_tokens,
            ),
            "output_token_count": max(
                0, self._output_tokens - self._baseline_output_tokens,
            ),
        }

    def delete_run(self, run_id: str, revision: int) -> None:
        body = json.dumps({
            "expected_revision": revision,
            "idempotency_key": self._key("smoke_delete"),
            "confirmed": True,
        }, separators=(",", ":")).encode("utf-8")
        self._request(
            "DELETE",
            self._run_path(run_id),
            body=body,
            content_type="application/json",
            expected_status=204,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one redacted localhost AI service smoke.")
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--service-url", required=True)
    parser.add_argument("--internal-token", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        client = HttpSmokeClient(arguments.service_url, arguments.internal_token)
        summary = execute_smoke(arguments.artifact_root, client)
    except SmokeFailure as error:
        sys.stderr.write(error.code + "\n")
        return 2
    except (KeyboardInterrupt, StopIteration):
        sys.stderr.write("SMOKE_INTERRUPTED\n")
        return 130
    except Exception:
        sys.stderr.write("SMOKE_FAILED\n")
        return 2
    write_summary(summary, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
