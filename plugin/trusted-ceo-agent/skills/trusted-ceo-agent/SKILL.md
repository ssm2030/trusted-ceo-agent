---
name: trusted-ceo-agent
description: Run an evidence-grounded CEO diagnostic workflow over company CSV, JSON, or XLSX inputs. Use when asked to discover important management issues, test cause and counter-hypotheses, prepare conditional responses or expert-review questions, or resume and validate a Trusted CEO Agent run.
---

# Trusted CEO Agent

Use the bundled deterministic CLI as the only trust boundary. Treat every model-written draft as untrusted.

## Start safely

1. Run `python plugin/trusted-ceo-agent/scripts/bootstrap.py preflight`.
2. Stop if preflight fails and show its remediation text. Never install or update packages automatically.
3. Run the engine only through:

   `uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py <command>`

4. Use an explicit artifact root inside the current workspace. Never use `logs`, the plugin directory, or an input directory.

## Follow the governed workflow

1. Use `preflight`, then `start`, then `status`. For an unconfirmed Mission, pass the stable application actor with `start --run-owner-actor-id`; the CLI binds it to the local transport principal without granting TTY approval authority. When a workflow state needs a user response, read the deterministic card with `pending-action`.
2. Use `scan`; if mapping is ambiguous, use `prepare-jobs --stage schema_mapping`, `ingest-result`, and `reduce-stage --stage schema_mapping`.
3. Use `approval-request --gate data` and wait for the user to run `approve-interactive` in a real terminal. If the reviewer requests changes or rejects the run, record that decision with `decide-interactive` instead of fabricating an approval.
4. Use `run-components` and `prepare-jobs --stage lens`.
5. Create one strict JSON draft per frozen Job, then use `ingest-result` and `reduce-stage --stage lens`.
6. After the Join Barrier, use `prepare-jobs --stage integrated`, `ingest-result`, and `reduce-stage --stage integrated` once.
7. Use `approval-request --gate diagnostic`. Run approved deep work only with `run-components`, optionally adding `--accounting-input <closed-request.json>` and `--professional-input <closed-request.json>` for the approved scope. These inputs are revision-bound, publish deterministic accounting and professional artifacts in the same revision, and block finalization when required work fails. Then use `prepare-jobs --stage deep_dive`, `ingest-result`, and `reduce-stage --stage deep_dive`.
8. Use `prepare-finalization`, `prepare-jobs --stage writer`, `ingest-result`, and `reduce-stage --stage writer`.
9. Use `approval-request --gate final`; wait for terminal `approve-interactive` or `decide-interactive`; then use `finalize` only after approval.
10. For an Analysis-affecting answer, call read-only `preview-human-response` first and then `submit-human-response` with the card ID, card content hash, current expected revision, strict response JSON, and a stable idempotency key. The bound local principal, actor/gate allowlist, and Source access policy must pass. A `request_explanation` response is read-only and uses a non-semantic operational idempotency receipt; every other accepted analysis response creates exactly one revision. A response never creates an Approval Record, so wait for the existing TTY approval commands when `terminal_approval_required` is returned.
11. Use `validate` and `render` on the finalized revision, then use read-only `export-web-report --revision <finalized> --output <workspace>/web-report-bundle.json` and `validate-web-report --revision <finalized> --bundle <workspace>/web-report-bundle.json` for the deterministic Tab 2 bundle. For a read-only result question, use `prepare-result-question`, run the isolated one-shot model, and display only the canonical answer returned by `validate-result-answer`. Use `resume`, `stop`, or `cancel` only with the current expected revision.

Read [workflow.md](references/workflow.md) for state and gate handling. Read [result-question.md](references/result-question.md) before a result question. Read [reasoning-contract.md](references/reasoning-contract.md) before creating any model draft.

## Enforce reasoning limits

- Use only IDs and claim types present in each Reasoning Job allowlist.
- Keep Fact, Signal, calculation, grade, and approval authority in the runtime.
- Retry only explicit host failure or invalid JSON, at most once for the same Job.
- Treat missing data, contradiction, professional triggers, and Not Assessable as outcomes, not retry reasons.
- Complete required challenge lenses before integration.
- Never compare causes, rank issues, resolve cross-issue relations, or write the CEO narrative before the Join Barrier.

## Never bypass the Trust Kernel

- Fact를 직접 생성하거나 수정하지 마라.
- Signal을 직접 생성하거나 수정하지 마라.
- 결과 등급을 직접 지정하지 마라.
- 승인을 자동 생성하거나 파일로 위조하지 마라.
- Never edit source snapshots, Pack authority, state pointers, Approval Records, hashes, or finalized files.
- Never read or write `logs`, the qualifying-round project, `submission.zip`, or POC oracles during a run.
- Never state a final accounting, tax, legal, labor, audit, or investment conclusion.

Every mutation must include the latest `--expected-revision`. On exit code 2, pause for human action or additional input. On 3, repair the contract input. On 4, stop for integrity or approval review. On 6, call `status` and rebuild the mutation from the current revision.
