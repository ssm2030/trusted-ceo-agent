from __future__ import annotations

import argparse
from pathlib import Path

from trusted_ceo_agent.questions.scope import SCOPE_KINDS


STAGES = ("schema_mapping", "lens", "integrated", "deep_dive", "writer")
GATES = ("context", "data", "scope_narrowing", "diagnostic", "final")

def _add_run(parser: argparse.ArgumentParser, *, mutation: bool = False) -> None:
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    if mutation:
        parser.add_argument("--expected-revision", type=int, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trusted-ceo-agent", description="Trusted CEO Agent")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")

    start = commands.add_parser("start")
    start.add_argument("--artifact-root", type=Path, required=True)
    start.add_argument("--mission-contract", type=Path, required=True)
    start.add_argument("--input", type=Path, action="append", required=True)
    start.add_argument("--run-owner-actor-id")

    for name in ("scan", "prepare-finalization", "finalize", "resume", "stop", "cancel"):
        _add_run(commands.add_parser(name), mutation=True)

    prepare = commands.add_parser("prepare-jobs")
    _add_run(prepare, mutation=True)
    prepare.add_argument("--stage", choices=STAGES, required=True)

    ingest = commands.add_parser("ingest-result")
    _add_run(ingest, mutation=True)
    ingest.add_argument("--job-id", required=True)
    ingest.add_argument("--draft", type=Path, required=True)

    reduce_stage = commands.add_parser("reduce-stage")
    _add_run(reduce_stage, mutation=True)
    reduce_stage.add_argument("--stage", choices=STAGES, required=True)

    approval_request = commands.add_parser("approval-request")
    _add_run(approval_request, mutation=True)
    approval_request.add_argument("--gate", choices=GATES, required=True)
    approval_request.add_argument("--overlay", type=Path, required=True)

    approve = commands.add_parser("approve-interactive")
    _add_run(approve, mutation=True)
    approve.add_argument("--request-id", required=True)

    decide = commands.add_parser("decide-interactive")
    _add_run(decide, mutation=True)
    decide.add_argument("--request-id", required=True)
    decide.add_argument("--decision", choices=("request_changes", "reject"), required=True)
    decide.add_argument(
        "--change-scope",
        choices=("data", "scan", "reasoning", "deep", "wording", "routing"),
    )

    components = commands.add_parser("run-components")
    _add_run(components, mutation=True)
    components.add_argument("--scope-ref", required=True)
    components.add_argument("--accounting-input", type=Path)
    components.add_argument("--professional-input", type=Path)

    prepare_accounting = commands.add_parser("prepare-accounting-input")
    _add_run(prepare_accounting)
    prepare_accounting.add_argument("--revision", type=int, required=True)
    prepare_accounting.add_argument("--source-id", required=True)
    prepare_accounting.add_argument("--scope-ref", required=True)
    prepare_accounting.add_argument("--output", type=Path, required=True)

    status = commands.add_parser("status")
    _add_run(status)

    validate = commands.add_parser("validate")
    _add_run(validate)
    validate.add_argument("--revision", type=int, required=True)

    render = commands.add_parser("render")
    _add_run(render)
    render.add_argument("--revision", type=int, required=True)

    export_web_report = commands.add_parser("export-web-report")
    _add_run(export_web_report)
    export_web_report.add_argument("--revision", type=int, required=True)
    export_web_report.add_argument("--output", type=Path, required=True)
    export_web_report.add_argument("--input-manifest", type=Path, required=True)

    validate_web_report = commands.add_parser("validate-web-report")
    _add_run(validate_web_report)
    validate_web_report.add_argument("--revision", type=int, required=True)
    validate_web_report.add_argument("--bundle", type=Path, required=True)

    prepare_question = commands.add_parser("prepare-result-question")
    _add_run(prepare_question)
    prepare_question.add_argument("--revision", type=int, required=True)
    prepare_question.add_argument("--question-file", type=Path, required=True)
    prepare_question.add_argument("--scope-kind", choices=sorted(SCOPE_KINDS), required=True)
    prepare_question.add_argument("--scope-instance-id", required=True)
    prepare_question.add_argument(
        "--privacy-classification",
        choices=("poc_deidentified", "company_restricted"),
        required=True,
    )

    validate_answer = commands.add_parser("validate-result-answer")
    _add_run(validate_answer)
    validate_answer.add_argument("--revision", type=int, required=True)
    validate_answer.add_argument("--job", type=Path, required=True)
    validate_answer.add_argument("--draft", type=Path, required=True)

    pending_action = commands.add_parser("pending-action")
    _add_run(pending_action)

    for name in ("preview-human-response", "submit-human-response"):
        human_response = commands.add_parser(name)
        _add_run(human_response, mutation=True)
        human_response.add_argument("--action-id", required=True)
        human_response.add_argument("--action-content-hash", required=True)
        human_response.add_argument("--response", type=Path, required=True)
        if name == "submit-human-response":
            human_response.add_argument("--idempotency-key", required=True)
    return parser
