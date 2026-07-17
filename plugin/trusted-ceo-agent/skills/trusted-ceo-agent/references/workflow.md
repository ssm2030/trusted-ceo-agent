# Workflow reference

## State ownership

The CLI owns state and revisions. Do not edit artifact files. Read the single JSON response on stdout and use stderr only as diagnostic context.

## Gate sequence

| Gate | Purpose | Continue only when |
|---|---|---|
| Context | Mission and customer claims | Mission is confirmed and claims remain hypotheses |
| Data | Mapping and source roles | Essential mappings and meanings are approved |
| Scope narrowing | Card limit and excluded scopes | At most six cards remain and every exclusion is a blind spot |
| Diagnostic | Issues, disputes, and deep scope | Every issue and decision proposal has a disposition |
| Final | Responses, expert routing, and wording | Every delivery item has a disposition |

`approval-request` creates a diff and one-time nonce only. It never approves. The user must run `approve-interactive` to approve, or `decide-interactive` to request changes or reject, with TTY stdin and stdout. A request expires after ten minutes and the nonce is single-use. Requesting changes invalidates the affected downstream approvals; rejection stops the run.

`pending-action` returns the current immutable Human Action Card without changing the revision. For an unconfirmed Mission, `start --run-owner-actor-id` binds the application actor to the local transport principal; it does not create approval authority. `preview-human-response` validates the card, policy, and response without mutation. `submit-human-response` records facts, meanings, scope choices, or change requests with CAS and idempotency after actor/gate and Source access-policy checks. A resolved card is not regenerated until workflow state or evidence changes. It cannot approve a gate; `terminal_approval_required` means the separate TTY approval flow is still required.

## Revision behavior

Pass `--expected-revision` to every mutation. If a command returns exit 6, call `status`, discard the stale proposal, and reconstruct it against the current snapshot. Do not merge snapshots manually.

`status`, `pending-action`, `preview-human-response`, `validate`, `render`, `export-web-report`, `validate-web-report`, `prepare-result-question`, and `validate-result-answer` are read-only. The web-report and result-question commands require an explicit finalized `--revision`; they never write into a snapshot or `logs`. `stop`, `cancel`, and `finalize` are terminal when accepted. `resume` is valid only when the recorded blocker is resolved.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Success |
| 2 | Human action or additional input required |
| 3 | Contract or Schema violation |
| 4 | Integrity or approval failure |
| 5 | Internal failure |
| 6 | Revision conflict |
