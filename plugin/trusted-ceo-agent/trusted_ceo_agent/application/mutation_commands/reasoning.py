from __future__ import annotations

from typing import Any, Mapping

from trusted_ceo_agent.application.mutation_reasoning import (
    _accepted_validation,
    _block_reasoning_failure,
    _deterministic_writer_fallback,
    _materialize_reasoning_draft,
    _reasoning_attempt_record,
    _reasoning_attempt_records,
    _reasoning_jobs,
)
from trusted_ceo_agent.application.mutation_session import MutationSession
from trusted_ceo_agent.application.mutation_support import advance as _advance
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.reasoning.attempts import next_attempt_action
from trusted_ceo_agent.reasoning.join import freeze_join_manifest, reduce_join


EXIT_CONTRACT = 3
COMMANDS = frozenset({"prepare-jobs", "ingest-result", "reduce-stage"})


def handle(session: MutationSession) -> bool:
    if session.args.command not in COMMANDS:
        return False
    args = session.args
    pointer = session.pointer
    current = session.current
    files = session.files
    state = session.state
    data = session.data
    exit_code = session.exit_code
    command_ok = session.command_ok
    command_message = session.command_message
    if args.command == "prepare-jobs":
        allowed_states = {
            "schema_mapping": {"schema_mapping_job_ready"},
            "integrated": {"lens_ready"},
            "deep_dive": {"deep_dive_jobs_ready"},
            "writer": {"finalization_jobs_ready"},
        }
        if args.stage != "lens" and state["state"] not in allowed_states[args.stage]:
            raise ContractError(f"prepare-jobs:{args.stage} is not allowed from {state['state']}")
        jobs = _reasoning_jobs(
            args.stage, files=files, pointer=pointer, run_id=args.run_id, revision=current,
        )
        if args.stage == "lens":
            state = _advance(state, "prepare_lens", {"estimated_card_count": len(jobs)})
            if state["state"] == "scope_narrowing_required":
                jobs = []
                exit_code = 2
        for job in jobs:
            SchemaStore().validate("reasoning-job.schema.json", job)
            files[f"tasks/{job['job_id']}/job.json"] = canonical_bytes(job)
        data["job_ids"] = [job["job_id"] for job in jobs]
    elif args.command == "ingest-result":
        job_path = f"tasks/{args.job_id}/job.json"
        if job_path not in files:
            raise ContractError(f"unknown Reasoning Job: {args.job_id}")
        job = strict_loads(files[job_path])
        if not isinstance(job, Mapping):
            raise IntegrityError(f"Reasoning Job is invalid: {args.job_id}")
        stage = job["stage"]
        accepted_source = args.draft_source
        if (
            accepted_source == "deterministic_canonical"
            and stage != "schema_mapping"
        ):
            raise ContractError(
                "deterministic_canonical source is only allowed for schema_mapping"
            )
        expected_states = {
            "schema_mapping": {"schema_mapping_job_ready"},
            "lens": {"lens_jobs_ready"},
            "integrated": {"lens_ready"},
            "deep_dive": {"deep_dive_jobs_ready"},
            "writer": {"finalization_jobs_ready"},
        }
        if state["state"] not in expected_states.get(stage, set()):
            raise ContractError(f"ingest-result:{stage} is not allowed from {state['state']}")
        validation_path = f"tasks/{args.job_id}/validation.json"
        if validation_path in files:
            current_validation = strict_loads(files[validation_path])
            if isinstance(current_validation, Mapping) and current_validation.get("valid") is True:
                raise ContractError(f"Reasoning Job already has an accepted result: {args.job_id}")
        attempts = _reasoning_attempt_records(files, args.job_id, stage)
        if len(attempts) >= 2:
            raise ContractError(f"Reasoning Job exhausted two attempts: {args.job_id}")
        attempt = len(attempts) + 1
        draft = args.draft.read_bytes()
        attempt_root = f"tasks/{args.job_id}/attempts/attempt-{attempt}"
        files[f"{attempt_root}.draft"] = draft

        failure_kind: str | None = None
        validation_error: str | None = None
        materialized_updates: dict[str, bytes] = {}
        materialized_data: dict[str, Any] = {}
        try:
            draft_document = strict_loads(draft)
        except (UnicodeError, ValueError) as error:
            failure_kind = "invalid_json"
            validation_error = str(error)
        else:
            try:
                if not isinstance(draft_document, Mapping):
                    raise ContractError("Reasoning draft must be an object")
                materialized_updates, materialized_data = _materialize_reasoning_draft(
                    job, draft_document, files,
                )
            except ContractError as error:
                failure_kind = "contract"
                validation_error = str(error)

        if failure_kind is None:
            action = "accepted"
            attempt_record = _reasoning_attempt_record(
                job, draft, attempt, valid=True, action=action,
            )
            files.update(materialized_updates)
            data.update(materialized_data)
            files[validation_path] = canonical_bytes(_accepted_validation(
                job, attempt, source=accepted_source, action=action,
            ))
        else:
            action = next_attempt_action(
                stage, attempt, required=True, failure_kind=failure_kind,
            )
            attempt_record = _reasoning_attempt_record(
                job,
                draft,
                attempt,
                valid=False,
                action=action,
                failure_kind=failure_kind,
                validation_errors=(validation_error or "draft validation failed",),
            )
            data["validation_errors"] = attempt_record["validation_errors"]
            files[validation_path] = canonical_bytes(attempt_record)
            if action == "deterministic_mapping":
                fallback = strict_loads(files["intake/canonical-mapping-proposal.json"])
                SchemaStore().validate("schema-mapping-draft.schema.json", fallback)
                files[f"tasks/{args.job_id}/draft.json"] = canonical_bytes(fallback)
                files[validation_path] = canonical_bytes(_accepted_validation(
                    job, attempt, source="deterministic_fallback", action=action,
                ))
            elif action == "fallback":
                fallback = _deterministic_writer_fallback(job)
                files[f"tasks/{args.job_id}/writer.json"] = canonical_bytes(fallback)
                files[validation_path] = canonical_bytes(_accepted_validation(
                    job, attempt, source="deterministic_fallback", action=action,
                ))
                data["writer_result_id"] = fallback["writer_result_id"]
            elif action == "blocked":
                state = _block_reasoning_failure(state, stage)
                exit_code = EXIT_CONTRACT
                command_ok = False
                command_message = "reasoning draft failed twice; workflow blocked"
            elif action == "retry":
                exit_code = EXIT_CONTRACT
                command_ok = False
                command_message = "reasoning draft validation failed; one retry remains"
            else:
                raise ContractError(f"unsupported Reasoning attempt action: {action}")
        files[f"{attempt_root}.json"] = canonical_bytes(attempt_record)
        data.update({
            "job_id": args.job_id,
            "attempt": attempt,
            "attempt_action": action,
        })
    elif args.command == "reduce-stage" and args.stage == "lens":
        jobs = []
        for path, payload in files.items():
            if path.startswith("tasks/") and path.endswith("/job.json"):
                job = strict_loads(payload)
                if job.get("stage") == "lens":
                    jobs.append(job)
        if not jobs:
            raise ContractError("no lens Jobs are prepared")
        tasks = [
            {
                "job_id": job["job_id"],
                "required": True,
                "required_signal_ids": job.get("required_signal_ids", []),
            }
            for job in jobs
        ]
        first = sorted(jobs, key=lambda item: item["job_id"])[0]
        manifest = freeze_join_manifest(
            first["artifact_ref"], first["mission_contract_hash"], first["pack_manifest_hash"],
            tasks, "1970-01-01T00:00:00Z",
        )
        results = []
        for job in jobs:
            card_path = f"tasks/{job['job_id']}/card.json"
            validation_path = f"tasks/{job['job_id']}/validation.json"
            validation = strict_loads(files.get(validation_path, b"{}"))
            if (
                card_path not in files
                or not isinstance(validation, Mapping)
                or validation.get("valid") is not True
                or validation.get("source") != "model_draft"
            ):
                raise ContractError(f"lens Job lacks a validated card: {job['job_id']}")
            card = strict_loads(files[card_path])
            status = "valid_not_assessable" if card.get("assessment_status") == "not_assessable" else "completed"
            results.append({"job_id": job["job_id"], "status": status, "card": card})
        joined = reduce_join(manifest, results)
        files["reasoning/join-manifest.json"] = canonical_bytes(manifest)
        files["reasoning/join-result.json"] = canonical_bytes(joined)
        data.update({"join_manifest_id": manifest["join_manifest_id"], "join_result_id": joined["join_result_id"]})
        state = _advance(state, "reduce_lens", {"required_tasks_accepted": True})
    elif args.command == "reduce-stage" and args.stage == "schema_mapping":
        candidates: list[tuple[bytes, Mapping[str, Any]]] = []
        for path, payload in files.items():
            if not path.startswith("tasks/") or not path.endswith("/draft.json"):
                continue
            job_path = path.replace("/draft.json", "/job.json")
            validation_path = path.replace("/draft.json", "/validation.json")
            if job_path not in files or validation_path not in files:
                continue
            candidate_job = strict_loads(files[job_path])
            validation = strict_loads(files[validation_path])
            if (
                isinstance(candidate_job, Mapping)
                and candidate_job.get("stage") == "schema_mapping"
                and isinstance(validation, Mapping)
                and validation.get("valid") is True
                and validation.get("source") in {
                    "model_draft",
                    "deterministic_canonical",
                    "deterministic_fallback",
                }
            ):
                candidates.append((payload, validation))
        if len(candidates) != 1:
            raise ContractError("schema_mapping reducer requires exactly one validated draft")
        proposal = strict_loads(candidates[0][0])
        SchemaStore().validate("schema-mapping-draft.schema.json", proposal)
        canonical_proposal = strict_loads(files["intake/canonical-mapping-proposal.json"])
        if canonical_bytes(proposal) != canonical_bytes(canonical_proposal):
            raise ContractError("schema mapping draft differs from the deterministic canonical proposal")
        files["reasoning/schema-mapping-proposal.json"] = canonical_bytes(proposal)
        data["reduction_source"] = candidates[0][1]["source"]
        state = _advance(state, "ingest_schema_mapping", {"draft_or_fallback_valid": True})
    elif args.command == "reduce-stage" and args.stage in {"integrated", "deep_dive", "writer"}:
        artifact_names = {
            "integrated": ("integrated.json", "reasoning/integrated-assessment.json", "integrated_assessment_id"),
            "deep_dive": ("deep-dive.json", "reasoning/deep-dive-result.json", "deep_dive_result_id"),
            "writer": ("writer.json", "reasoning/writer-result.json", "writer_result_id"),
        }
        leaf, destination, identifier_key = artifact_names[args.stage]
        candidates: list[tuple[dict[str, Any], Mapping[str, Any]]] = []
        for path, payload in files.items():
            if path.startswith("tasks/") and path.endswith(f"/{leaf}"):
                task_root = path.rsplit("/", 1)[0]
                job_path = f"{task_root}/job.json"
                validation_path = f"{task_root}/validation.json"
                if job_path not in files or validation_path not in files:
                    continue
                candidate_job = strict_loads(files[job_path])
                validation = strict_loads(files[validation_path])
                materialized = strict_loads(payload)
                allowed_sources = (
                    {"model_draft", "deterministic_fallback"}
                    if args.stage == "writer" else {"model_draft"}
                )
                if (
                    isinstance(candidate_job, Mapping)
                    and candidate_job.get("stage") == args.stage
                    and isinstance(validation, Mapping)
                    and validation.get("valid") is True
                    and validation.get("source") in allowed_sources
                    and isinstance(materialized, dict)
                ):
                    candidates.append((materialized, validation))
        if len(candidates) != 1:
            raise ContractError(f"{args.stage} reducer requires exactly one validated result")
        materialized, validation = candidates[0]
        files[destination] = canonical_bytes(materialized)
        data[identifier_key] = materialized[identifier_key]
        data["reduction_source"] = validation["source"]
        events = {
            "integrated": ("ingest_integrated", {"barrier_and_draft_valid": True}),
            "deep_dive": ("ingest_deep_result", {"required_deep_valid": True}),
            "writer": ("ingest_writer", {"grade_and_writer_valid": True}),
        }
        if args.stage == "writer" and validation["source"] == "deterministic_fallback":
            event, event_context = (
                "writer_fallback", {"fallback_valid_after_two_attempts": True},
            )
        else:
            event, event_context = events[args.stage]
        state = _advance(state, event, event_context)
    session.files = files
    session.state = state
    session.data = data
    session.exit_code = exit_code
    session.command_ok = command_ok
    session.command_message = command_message
    return True
