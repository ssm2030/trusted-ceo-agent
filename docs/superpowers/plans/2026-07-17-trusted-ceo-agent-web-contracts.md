# Trusted CEO Agent Web Contract and Plugin Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze Contract 0 and add deterministic, read-only `export-web-report` and `validate-web-report` plugin commands that turn one fully validated immutable revision into a cross-validated web viewer bundle.

**Architecture:** The repository-level `contracts/web-report/v1` directory is the only wire-contract source for Python and TypeScript. The plugin reuses its existing snapshot, Evidence Core, Grade Record, Final Result, approval, and package validators; it then derives a bounded evidence closure, presentation instructions, source previews, trust history, expert packets, and revision comparison without adding analytical judgment. Registered bundles are trusted only when `validate-web-report` independently re-exports the registered full run and proves byte equality, hashes, workflow state, approval ancestry, and required validation checks.

**Tech Stack:** Python 3.11, standard-library `unittest`, `jsonschema` Draft 2020-12, `rfc8785==0.1.4`, SHA-256, existing immutable `ArtifactStore`, Node.js, `json-schema-to-typescript==15.0.4`, TypeScript.

---

## Source of truth and execution boundaries

Read these two approved documents together before implementation:

- `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-web-design-final.md`
- `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-web-design-final-addendum-v2.md`

This plan owns:

1. all six Contract 0 schemas, the generated TypeScript types, and the named valid/invalid fixtures;
2. RFC 8785 JCS and SHA-256 bundle hashing;
3. reusable full-revision validation;
4. evidence closure, source previews, presentation manifest, trust view, expert packet view, and revision view;
5. plugin `export-web-report` and `validate-web-report`;
6. an automated simulated-TTY integration test and a separate actual-terminal golden-run acceptance.

This plan does not own:

- the Next.js viewer implementation;
- Codex result Q&A execution;
- live `AnalysisProvider`;
- Vercel, Supabase, public deployment, or authentication.

Every plugin invocation in tests, runbooks, and manual acceptance uses this launcher:

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py <command>
```

Do not import plugin Python modules from the web application. Do not make `export-web-report` or `validate-web-report` mutations. Do not create a web approval command.

## File map

### Shared Contract 0

```text
contracts/web-report/
  package.json
  package-lock.json
  scripts/
    generate-types.mjs
  v1/
    web-report-contracts.schema.json
    web-report-bundle.schema.json
    viewer-eligibility-decision.schema.json
    presentation-manifest.schema.json
    result-question-job.schema.json
    result-answer-draft.schema.json
    result-answer.schema.json
    generated/
      types.ts
    fixtures/
      valid-trusted.json
      valid-poc.json
      valid-unverified-import.json
      invalid-hash.json
      invalid-reference.json
      oversize.json
      jcs-hash-vectors.json
```

Responsibilities:

- `web-report-bundle.schema.json`: complete immutable viewer payload and all embedded view definitions.
- `viewer-eligibility-decision.schema.json`: trusted/POC/unverified/rejected decision returned to the server.
- `presentation-manifest.schema.json`: plugin-owned summary order, metrics, charts, issue graph, and Korean labels.
- `result-question-job.schema.json`: later Q&A input closure; Contract 0 freezes it now.
- `result-answer-draft.schema.json`: untrusted Codex answer template and citations.
- `result-answer.schema.json`: plugin-validated canonical answer.
- `web-report-contracts.schema.json`: generation-only root referencing all six public schemas.
- `generated/types.ts`: schema-generated exports, including the exact viewer imports listed below.
- `oversize.json`: a compact fixture descriptor that tells the test to synthesize `52_428_801` bytes; it must not be a 50 MiB committed file.

The generated file must export at least:

```ts
export interface WebReportBundleV1 {}
export interface ViewerEligibilityDecisionV1 {}
export interface PresentationManifestV1 {}
export interface SourcePreviewV1 {}
export interface ExpertPacketViewItemV1 {}
export interface RevisionViewV1 {}
export interface ResultQuestionJobV1 {}
export interface ResultAnswerDraftV1 {}
export interface ResultAnswerV1 {}
```

The empty bodies above state names only. The generated output contains every schema-derived field and must not contain `any` or an open `unknown` property bag.

### Plugin production code

```text
plugin/trusted-ceo-agent/
  pyproject.toml
  uv.lock
  skills/trusted-ceo-agent/
    SKILL.md
    references/workflow.md
  trusted_ceo_agent/
    cli.py
    trust/
      revision_validation.py
    web_report/
      __init__.py
      canonical.py
      contracts.py
      closure.py
      previews.py
      presentation.py
      expert_packets.py
      revisions.py
      exporter.py
      eligibility.py
```

Responsibilities:

- `revision_validation.py`: the existing `validate` logic extracted behind a reusable result type.
- `canonical.py`: RFC 8785 only; do not change the engine's existing `canonical.py`.
- `contracts.py`: bounded parse, schema validation, semantic reference validation, and hash validation.
- `closure.py`: transitive issue → Evidence Link → Signal → Fact → Source closure.
- `previews.py`: locator-bound, access-policy-bound embedded previews.
- `presentation.py`: deterministic display order and conservative chart instructions.
- `expert_packets.py`: accepted one-way packet expansion from immutable approved artifacts.
- `revisions.py`: manifest ancestry, trust events, file manifest, and prior-final comparison.
- `exporter.py`: validated bundle assembly; no filesystem output side effects.
- `eligibility.py`: registered full-run cross-validation and schema-valid eligibility decisions.
- `cli.py`: argument parsing, stable input reads, safe output writes, and response envelopes only.

### Tests and demo evidence

```text
tests/
  web_report_support.py
  contracts/
    test_web_report_contract_schemas.py
    test_web_report_jcs.py
    test_web_report_contract_semantics.py
  unit/
    trust/
      __init__.py
      test_revision_validation.py
    web_report/
      __init__.py
      test_closure.py
      test_previews.py
      test_presentation.py
      test_expert_packets.py
      test_revisions.py
      test_exporter.py
      test_eligibility.py
  integration/
    test_cli_web_report.py
  safety/
    test_web_report_boundaries.py
  plugin/
    test_cli_commands.py
    test_skill_cli_parity.py
docs/runbooks/
  trusted-ceo-agent-actual-tty-golden-web-report.md
demo/web-report/golden/
  README.md
  web-report-bundle.json
  validation-decision.json
```

The actual full-run artifact root stays under the already ignored `artifacts/` directory because it contains the server-only source resolver. Only the absolute-path-free bundle and eligibility decision are committed.

## Exact Contract 0 vocabulary

Use the following names verbatim across schemas, Python, fixtures, generated TypeScript, and the web viewer.

### Bundle root

```text
bundle_version
canonicalization_version
run
viewer_eligibility_receipt
final_result
presentation_manifest
evidence_view
source_view
source_previews
official_url_policy
trust_view
expert_packet_view
revision_view
file_manifest
bundle_hash
```

Constants:

```text
bundle_version = "1.0.0"
canonicalization_version = "rfc8785-jcs-1"
maximum bundle bytes = 52_428_800
maximum issues = 500
maximum charts = 50
maximum points per chart = 5_000
maximum JCS bytes of all source_previews = 10_485_760
maximum answer blocks = 12
maximum answer-block text_template length = 800
```

### Run and receipt

```text
run:
  run_id
  revision
  workflow_state
  semantic_fingerprint
  finalization_event_time

viewer_eligibility_receipt:
  receipt_version
  claimed_viewer_mode
  run_id
  approved_revision
  finalized_revision
  workflow_state
  snapshot_manifest_hash
  final_result_hash
  result_artifact_ref
  revision_ancestry_hash
  validator_version
  completed_checks
  final_approval_summary
```

Enums:

```text
claimed_viewer_mode = trusted_final | poc_fixture | unverified_import
workflow_state = finalized
```

All receipt fields are evidence to be cross-validated; the receipt is never sufficient to award a badge.

### Eligibility decision

```text
decision_version
eligible
viewer_mode
badge_label_ko
run_id
revision
bundle_hash
completed_checks
failure_code
failure_message
```

Enums and labels:

```text
trusted_final      -> 승인·검증된 실행본
poc_fixture        -> 검증된 POC 시연 실행본
unverified_import  -> 출처 미확인 묶음
rejected           -> 열 수 없는 묶음
```

Failure codes:

```text
BUNDLE_SIZE_EXCEEDED
BUNDLE_JSON_INVALID
BUNDLE_SCHEMA_INVALID
BUNDLE_HASH_MISMATCH
REFERENCE_CLOSURE_BROKEN
RUN_ID_MISMATCH
REVISION_MISMATCH
WORKFLOW_NOT_FINALIZED
REQUIRED_CHECK_MISSING
FINAL_APPROVAL_INVALID
ANCESTRY_MISMATCH
FULL_RUN_MISMATCH
BYTE_MISMATCH
ABSOLUTE_PATH_LEAK
```

`failure_code` and `failure_message` are required nullable strings. An eligible decision has both set to `null`. A rejected decision has both non-null.

### Presentation manifest

```text
ceo_summary_issue_refs
selection_basis
metric_cards
chart_specs
issue_graph
korean_labels
```

`selection_basis` is the constant `grade_order_then_issue_id`. Grade order is:

```text
Decision Required
Immediate Verification
Expert Review Required
Monitor
Appendix Signal
Not Assessable
```

The stable `issue_id` tie-break is presentation order, not a claim that one equal-grade issue is more important.

Metric cards:

```text
metric_card_id
issue_ref
label_ko
value_ref
display_value
unit_code
currency_code
```

Chart specs:

```text
chart_id
title_ko
chart_kind
issue_refs
x_axis_label_ko
y_axis_label_ko
unit_code
points
```

Each point:

```text
point_id
x_label
value_ref
display_value
evidence_link_ids
```

`chart_kind` v1 is `line`. `display_value` is a canonical string, never a binary floating-point JSON number. The web only renders these instructions.

Issue graph:

```text
nodes: issue_ref, label_ko, grade
edges: relation_id, from_issue_ref, to_issue_ref, relation_type
```

### Evidence and source views

```text
evidence_view:
  facts
  signals
  evidence_links
  data_quality
  capability_map
  issue_claim_closure

source_view[]:
  source_ref
  display_name_ko
  snapshot_locator
  extraction_hashes
  locator_summaries
  access_policy
  official_url
  preview_refs

source_previews[]:
  preview_ref
  source_ref
  locator
  column_labels
  rows
  truncated
  truncation_reason
  masking_status
  access_policy
  preview_hash
```

`snapshot_locator` is the immutable logical `sources/blobs/<sha256>` reference, never an OS path. `official_url` is required nullable. `rows` contain only JSON scalars. `restricted` and `prohibited` previews always have empty `column_labels` and `rows`. A budget-truncated `permitted` preview keeps its locator and sets `truncated=true`, `truncation_reason="bundle_preview_budget"`, and `rows=[]`.

### Trust, packet, and revision views

```text
trust_view:
  plugin_version
  pack_versions
  schema_versions
  validator_version
  completed_checks
  approval_summary
  trust_events
  file_hashes
  limitations
  deidentification

trust_event:
  event_id
  revision
  command
  actor_kind
  gate
  sequence
  timestamp
  invalidated_approval_refs
```

`gate` and `timestamp` are required nullable. Missing immutable timestamps remain `null`; export time is never substituted.

```text
expert_packet_view[]:
  expert_packet_id
  profession
  target_issue_ref
  fact_refs
  evidence_link_ids
  source_refs
  cause_hypotheses
  counter_hypotheses
  unresolved_uncertainties
  required_document_refs
  review_question
  forbidden_conclusions
  source_locators
  run_id
  revision
  packet_hash
```

```text
revision_view:
  available
  unavailable_reason
  base_revision
  compare_revision
  change_categories
  added_refs
  changed_refs
  removed_refs
  invalidated_approval_refs
  previous_semantic_fingerprint
  current_semantic_fingerprint
  display_message_ko
```

All nullable revision fields are present. When no earlier finalized result exists, `available=false`, `unavailable_reason="NO_PRIOR_FINAL_RESULT"`, `base_revision=null`, and all change arrays are empty.

### Question contracts frozen in Contract 0

`ResultQuestionJobV1` uses:

```text
job_version
job_id
run_id
revision
question
response_locale
scope
allowed_issue_refs
allowed_claim_refs
allowed_fact_refs
allowed_signal_refs
allowed_evidence_link_ids
allowed_source_refs
allowed_value_refs
forbidden_conclusions
not_assessable_conditions
deidentification
context_caps
excluded_summary
output_schema_version
```

Scope fields:

```text
scope_kind = run | issue | section | claim | evidence | source | expert_packet | revision_diff
scope_instance_id
start_refs
issue_id
```

`issue_id` is required nullable metadata and does not replace `scope_instance_id`.

`ResultAnswerDraftV1.answer_blocks[]` uses:

```text
block_id
support_status
text_template
value_refs
claim_refs
evidence_link_ids
source_refs
```

`support_status = supported | not_supported`. The only placeholder grammar is `{{value:<value_ref>}}`. `not_supported` text is exactly:

```text
현재 실행본의 근거로는 확인할 수 없습니다
```

`ResultAnswerV1.answer_blocks[]` replaces `text_template` with escaped plain UTF-8 `text` and retains resolved reference metadata. These schemas are implemented now; their runtime preparation and validation commands belong to the Q&A plan.

## Task 1: Freeze the six Draft 2020-12 schemas

**Files:**

- Create: `contracts/web-report/v1/web-report-bundle.schema.json`
- Create: `contracts/web-report/v1/viewer-eligibility-decision.schema.json`
- Create: `contracts/web-report/v1/presentation-manifest.schema.json`
- Create: `contracts/web-report/v1/result-question-job.schema.json`
- Create: `contracts/web-report/v1/result-answer-draft.schema.json`
- Create: `contracts/web-report/v1/result-answer.schema.json`
- Create: `contracts/web-report/v1/web-report-contracts.schema.json`
- Create: `tests/contracts/test_web_report_contract_schemas.py`

- [ ] **Step 1: Write the failing schema inventory and strict-object test**

```python
SCHEMAS = {
    "web-report-bundle.schema.json": "WebReportBundleV1",
    "viewer-eligibility-decision.schema.json": "ViewerEligibilityDecisionV1",
    "presentation-manifest.schema.json": "PresentationManifestV1",
    "result-question-job.schema.json": "ResultQuestionJobV1",
    "result-answer-draft.schema.json": "ResultAnswerDraftV1",
    "result-answer.schema.json": "ResultAnswerV1",
}

def walk_objects(value):
    if isinstance(value, dict):
        if value.get("type") == "object":
            yield value
        for child in value.values():
            yield from walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_objects(child)

class WebReportContractSchemaTests(unittest.TestCase):
    def test_public_schemas_are_draft_2020_12_and_closed(self) -> None:
        for name, title in SCHEMAS.items():
            schema = json.loads((CONTRACT_ROOT / name).read_text("utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            self.assertEqual(title, schema["title"])
            Draft202012Validator.check_schema(schema)
            for object_schema in walk_objects(schema):
                self.assertIs(False, object_schema.get("additionalProperties"), object_schema)
                properties = set(object_schema.get("properties", {}))
                self.assertEqual(properties, set(object_schema.get("required", [])), object_schema)
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.contracts.test_web_report_contract_schemas -v
```

Expected: FAIL because `contracts/web-report/v1` does not exist.

- [ ] **Step 3: Create the schemas with the exact vocabulary above**

Every schema starts with:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "web-report-bundle.schema.json",
  "title": "WebReportBundleV1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "bundle_version",
    "canonicalization_version",
    "run",
    "viewer_eligibility_receipt",
    "final_result",
    "presentation_manifest",
    "evidence_view",
    "source_view",
    "source_previews",
    "official_url_policy",
    "trust_view",
    "expert_packet_view",
    "revision_view",
    "file_manifest",
    "bundle_hash"
  ]
}
```

Use the field lists in “Exact Contract 0 vocabulary” as the complete required-property list for every object. Apply these constraints:

```text
bundle_version const "1.0.0"
canonicalization_version const "rfc8785-jcs-1"
sha256 pattern ^[0-9a-f]{64}$
run_id pattern ^run_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{16}$ for registered runs
issue arrays maxItems 500
chart_specs maxItems 50
chart points maxItems 5000
answer_blocks maxItems 12
text_template maxLength 800
all ID strings minLength 1
all ID-set arrays uniqueItems true
all unknown enum values rejected
```

Give the nested definitions these explicit `title` values so type generation exports them:

```text
SourcePreviewV1
ExpertPacketViewItemV1
RevisionViewV1
MetricCardV1
ChartSpecV1
ChartPointV1
TrustEventV1
```

Copy the current plugin Fact, Signal, Evidence Link, Data Quality, capability, final issue, relation, response, monitoring, blind-spot, and expert packet fields into closed Contract 0 `$defs`. Do not `$ref` outside `contracts/web-report/v1`; the contract must stand alone. Normalize currently optional Final approval summary fields as required nullable fields:

```text
gate
status
input_method
fixture_only
approval_id
actor_role
result_artifact_ref
```

`web-report-contracts.schema.json` is a closed generation-only object with six required properties, each `$ref`ing one public schema.

- [ ] **Step 4: Run the schema test and verify GREEN**

Run the Step 2 command.

Expected: all schema inventory and strict-object tests PASS.

- [ ] **Step 5: Commit Contract 0 schema vocabulary**

```text
git add contracts/web-report/v1/*.schema.json tests/contracts/test_web_report_contract_schemas.py
git commit -m "feat: freeze web report contract schemas"
```

## Task 2: Add RFC 8785 JCS without changing engine canonicalization

**Files:**

- Modify: `plugin/trusted-ceo-agent/pyproject.toml`
- Modify: `plugin/trusted-ceo-agent/uv.lock`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/__init__.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/canonical.py`
- Create: `contracts/web-report/v1/fixtures/jcs-hash-vectors.json`
- Create: `tests/contracts/test_web_report_jcs.py`

- [ ] **Step 1: Write failing RFC vectors and field-omission tests**

```python
from trusted_ceo_agent.web_report.canonical import jcs_bytes, jcs_sha256

class WebReportJcsTests(unittest.TestCase):
    def test_rfc8785_number_and_property_order_vector(self) -> None:
        value = {
            "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27],
            "string": "\u20ac$\u000f\nA'B\"\\\\\"/",
            "literals": [None, True, False],
        }
        self.assertEqual(
            EXPECTED_CANONICAL_UTF8,
            jcs_bytes(value),
        )

    def test_hash_can_omit_only_the_named_root_field(self) -> None:
        value = {"a": 1, "bundle_hash": "f" * 64, "nested": {"bundle_hash": "keep"}}
        expected = hashlib.sha256(
            jcs_bytes({"a": 1, "nested": {"bundle_hash": "keep"}})
        ).hexdigest()
        self.assertEqual(expected, jcs_sha256(value, omit_root_field="bundle_hash"))
```

Put the complete RFC vector input, canonical UTF-8 text, and SHA-256 into `jcs-hash-vectors.json`. Include property ordering, escaped controls, Unicode, `-0.0`, exponent formatting, and a nested field that must not be omitted.

- [ ] **Step 2: Run and verify RED**

Run:

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.contracts.test_web_report_jcs -v
```

Expected: FAIL because `trusted_ceo_agent.web_report.canonical` is missing.

- [ ] **Step 3: Pin the audited JCS implementation**

Add exactly:

```toml
"rfc8785==0.1.4",
```

to project dependencies, then regenerate the lock:

```text
uv lock --project plugin/trusted-ceo-agent
```

- [ ] **Step 4: Implement the isolated JCS API**

```python
from __future__ import annotations

import hashlib
from copy import deepcopy
from decimal import Decimal
from typing import Any, Mapping

import rfc8785


def _compatible(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite JSON number is forbidden")
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {str(key): _compatible(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_compatible(child) for child in value]
    return value


def jcs_bytes(value: Any) -> bytes:
    return rfc8785.dumps(_compatible(value))


def jcs_sha256(
    value: Mapping[str, Any],
    *,
    omit_root_field: str | None = None,
) -> str:
    body = deepcopy(dict(value))
    if omit_root_field is not None:
        body.pop(omit_root_field, None)
    return hashlib.sha256(jcs_bytes(body)).hexdigest()
```

Keep `trusted_ceo_agent/canonical.py` unchanged because engine snapshots already depend on its existing bytes.

- [ ] **Step 5: Run focused and full canonical tests**

Run:

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.contracts.test_web_report_jcs tests.unit.test_canonical -v
```

Expected: PASS.

- [ ] **Step 6: Commit JCS support**

```text
git add plugin/trusted-ceo-agent/pyproject.toml plugin/trusted-ceo-agent/uv.lock plugin/trusted-ceo-agent/trusted_ceo_agent/web_report tests/contracts/test_web_report_jcs.py contracts/web-report/v1/fixtures/jcs-hash-vectors.json
git commit -m "feat: add RFC 8785 web report hashing"
```

## Task 3: Add bounded contract parsing, semantic closure checks, and fixtures

**Files:**

- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/contracts.py`
- Create: `tests/web_report_support.py`
- Create: `tests/contracts/test_web_report_contract_semantics.py`
- Create: `contracts/web-report/v1/fixtures/valid-trusted.json`
- Create: `contracts/web-report/v1/fixtures/valid-poc.json`
- Create: `contracts/web-report/v1/fixtures/valid-unverified-import.json`
- Create: `contracts/web-report/v1/fixtures/invalid-hash.json`
- Create: `contracts/web-report/v1/fixtures/invalid-reference.json`
- Create: `contracts/web-report/v1/fixtures/oversize.json`

- [ ] **Step 1: Write failing valid/invalid fixture tests**

```python
from trusted_ceo_agent.web_report.contracts import (
    MAX_BUNDLE_BYTES,
    WebReportContractError,
    load_bundle_bytes,
    validate_bundle_document,
)

class WebReportContractSemanticTests(unittest.TestCase):
    def test_three_viewer_modes_are_valid(self) -> None:
        for name in ("valid-trusted.json", "valid-poc.json", "valid-unverified-import.json"):
            payload = (FIXTURES / name).read_bytes()
            document = load_bundle_bytes(payload)
            validate_bundle_document(document)

    def test_wrong_hash_and_dangling_reference_are_rejected_separately(self) -> None:
        with self.assertRaisesRegex(WebReportContractError, "bundle hash"):
            load_bundle_bytes((FIXTURES / "invalid-hash.json").read_bytes())
        with self.assertRaisesRegex(WebReportContractError, "unknown Evidence Link"):
            load_bundle_bytes((FIXTURES / "invalid-reference.json").read_bytes())

    def test_size_is_rejected_before_json_parse(self) -> None:
        with self.assertRaisesRegex(WebReportContractError, "52_428_800"):
            load_bundle_bytes(b" " * (MAX_BUNDLE_BYTES + 1))
```

- [ ] **Step 2: Run and verify RED**

Run:

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.contracts.test_web_report_contract_semantics -v
```

Expected: FAIL because the contract loader and fixtures do not exist.

- [ ] **Step 3: Implement the contract API and exact limits**

```python
CONTRACT_ROOT = Path(__file__).resolve().parents[4] / "contracts" / "web-report" / "v1"
MAX_BUNDLE_BYTES = 52_428_800
MAX_ISSUES = 500
MAX_CHARTS = 50
MAX_CHART_POINTS = 5_000
MAX_PREVIEW_BYTES = 10_485_760

class WebReportContractError(ContractError):
    pass

def load_bundle_bytes(payload: bytes) -> dict[str, Any]:
    if len(payload) > MAX_BUNDLE_BYTES:
        raise WebReportContractError(
            f"web report bundle exceeds 52_428_800 bytes: {len(payload)}"
        )
    try:
        value = strict_loads(payload)
    except (UnicodeError, ValueError) as error:
        raise WebReportContractError(f"invalid web report JSON: {error}") from error
    if not isinstance(value, dict):
        raise WebReportContractError("web report bundle must be an object")
    SchemaStore(CONTRACT_ROOT).validate("web-report-bundle.schema.json", value)
    validate_bundle_document(value)
    return value

def validate_bundle_document(bundle: Mapping[str, Any]) -> None:
    ...

def validate_eligibility_decision(decision: Mapping[str, Any]) -> None:
    SchemaStore(CONTRACT_ROOT).validate(
        "viewer-eligibility-decision.schema.json", decision
    )
```

Implement `validate_bundle_document` as deterministic checks in this order:

1. constants and array caps;
2. unique IDs in issues, relations, Facts, Signals, Evidence Links, Sources, previews, packets, and trust events;
3. every issue Evidence Link exists;
4. every Evidence Link target and evidence ref exists;
5. every Signal input Fact exists;
6. every derived Fact input Fact exists;
7. every Fact source ref exists;
8. every Source preview ref exists and points back to that Source;
9. every presentation issue/value/evidence ref exists;
10. every expert packet issue/fact/evidence/source ref exists;
11. every revision object ref exists in the current or prior-ref namespace declared by the bundle;
12. every `preview_hash` equals JCS SHA-256 with only its root `preview_hash` removed;
13. all source preview JCS bytes total no more than 10 MiB;
14. `bundle_hash` equals JCS SHA-256 with only root `bundle_hash` removed;
15. reuse `validate_no_absolute_paths` to reject OS absolute paths anywhere in the bundle.

Do not call this function “trust validation.” It proves the bundle's internal contract only.

- [ ] **Step 4: Build minimal but complete fixtures**

`tests/web_report_support.py` exports:

```python
def minimal_bundle(mode: str = "trusted_final") -> dict[str, Any]:
    ...

def with_bundle_hash(bundle: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(bundle))
    result["bundle_hash"] = jcs_sha256(result, omit_root_field="bundle_hash")
    return result
```

Use one issue, one Fact, one Evidence Link, one permitted Source, one preview, one metric card, and no chart in the valid fixtures. Differences:

```text
valid-trusted.json:
  claimed_viewer_mode trusted_final
  final approval input_method interactive_tty
  fixture_only false

valid-poc.json:
  claimed_viewer_mode poc_fixture
  final approval input_method test_fixture
  fixture_only true

valid-unverified-import.json:
  claimed_viewer_mode unverified_import
  viewer receipt approval fields null
  trust limitations include registered_full_run_unavailable
```

`invalid-hash.json` is `valid-trusted.json` with only `bundle_hash` replaced by 64 zeroes. `invalid-reference.json` contains an unknown issue Evidence Link and then has its outer bundle hash recomputed so the reference failure is observed before no unrelated hash failure. `oversize.json` is:

```json
{
  "fixture_kind": "generated_oversize",
  "base_fixture": "valid-trusted.json",
  "target_bytes": 52428801
}
```

- [ ] **Step 5: Run contract tests**

Run:

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.contracts.test_web_report_contract_schemas tests.contracts.test_web_report_jcs tests.contracts.test_web_report_contract_semantics -v
```

Expected: PASS.

- [ ] **Step 6: Commit bounded contract validation**

```text
git add contracts/web-report/v1/fixtures tests/web_report_support.py tests/contracts/test_web_report_contract_semantics.py plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/contracts.py
git commit -m "feat: validate bounded web report bundles"
```

## Task 4: Generate TypeScript from the frozen schemas and detect drift

**Files:**

- Create: `contracts/web-report/package.json`
- Create: `contracts/web-report/package-lock.json`
- Create: `contracts/web-report/scripts/generate-types.mjs`
- Create: `contracts/web-report/v1/generated/types.ts`
- Modify: `tests/contracts/test_web_report_contract_schemas.py`

- [ ] **Step 1: Add a failing generated-type inventory test**

```python
def test_generated_types_export_required_contract_names(self) -> None:
    text = (CONTRACT_ROOT / "generated" / "types.ts").read_text("utf-8")
    for name in (
        "WebReportBundleV1",
        "ViewerEligibilityDecisionV1",
        "PresentationManifestV1",
        "SourcePreviewV1",
        "ExpertPacketViewItemV1",
        "RevisionViewV1",
        "ResultQuestionJobV1",
        "ResultAnswerDraftV1",
        "ResultAnswerV1",
    ):
        self.assertRegex(text, rf"export (?:interface|type) {name}\b")
    self.assertNotRegex(text, r"\bany\b")
```

- [ ] **Step 2: Run and verify RED**

Run the Task 1 schema test command.

Expected: FAIL because `generated/types.ts` is absent.

- [ ] **Step 3: Pin the generator**

Create:

```json
{
  "name": "trusted-ceo-web-report-contracts",
  "private": true,
  "type": "module",
  "scripts": {
    "generate": "node scripts/generate-types.mjs",
    "generate:check": "node scripts/generate-types.mjs --check"
  },
  "devDependencies": {
    "json-schema-to-typescript": "15.0.4"
  }
}
```

Run:

```text
npm install --prefix contracts/web-report
```

Commit `package-lock.json`; never use unpinned `npx`.

- [ ] **Step 4: Implement deterministic generation and check mode**

```javascript
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import process from "node:process";
import { compileFromFile } from "json-schema-to-typescript";

const root = resolve(import.meta.dirname, "..");
const input = resolve(root, "v1", "web-report-contracts.schema.json");
const output = resolve(root, "v1", "generated", "types.ts");
const banner = [
  "/* eslint-disable */",
  "/** Generated from Contract 0. Do not edit by hand. */",
  "",
].join("\n");
const generated = await compileFromFile(input, {
  cwd: resolve(root, "v1"),
  bannerComment: banner,
  additionalProperties: false,
  declareExternallyReferenced: true,
  enableConstEnums: false,
  unreachableDefinitions: true,
  style: { singleQuote: false, semi: true, tabWidth: 2 },
});

if (process.argv.includes("--check")) {
  const current = await readFile(output, "utf8");
  if (current !== generated) {
    console.error("contracts/web-report/v1/generated/types.ts is stale");
    process.exit(1);
  }
} else {
  await mkdir(resolve(root, "v1", "generated"), { recursive: true });
  await writeFile(output, generated, "utf8");
}
```

- [ ] **Step 5: Generate and verify drift**

Run:

```text
npm run generate --prefix contracts/web-report
npm run generate:check --prefix contracts/web-report
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.contracts.test_web_report_contract_schemas -v
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit generated types**

```text
git add contracts/web-report/package.json contracts/web-report/package-lock.json contracts/web-report/scripts/generate-types.mjs contracts/web-report/v1/generated/types.ts tests/contracts/test_web_report_contract_schemas.py
git commit -m "build: generate web report contract types"
```

## Task 5: Extract reusable full-revision validation

**Files:**

- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/trust/revision_validation.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/cli.py`
- Create: `tests/unit/trust/__init__.py`
- Create: `tests/unit/trust/test_revision_validation.py`
- Modify: `tests/integration/test_cli_finalization_flow.py`

- [ ] **Step 1: Write a failing test for the reusable result**

```python
from trusted_ceo_agent.trust.revision_validation import (
    REQUIRED_WEB_REPORT_CHECKS,
    RevisionValidation,
    validate_revision,
)

def test_finalized_revision_returns_files_manifest_and_required_checks(self) -> None:
    store, run_id, revision = finalized_test_run(self.temp_root)
    result = validate_revision(store, revision)
    self.assertIsInstance(result, RevisionValidation)
    self.assertEqual(revision, result.revision)
    self.assertTrue(REQUIRED_WEB_REPORT_CHECKS <= set(result.checks))
    self.assertIn("final/result.json", result.files)
    self.assertEqual(revision, result.snapshot_manifest["revision"])
```

Required checks:

```python
REQUIRED_WEB_REPORT_CHECKS = frozenset({
    "snapshot_manifest",
    "evidence_core",
    "grade_recomputation",
    "final_package",
})
```

- [ ] **Step 2: Run and verify RED**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.trust.test_revision_validation -v
```

Expected: FAIL because `revision_validation.py` is missing.

- [ ] **Step 3: Move, do not duplicate, the existing `_validate` logic**

```python
@dataclass(frozen=True)
class RevisionValidation:
    revision: int
    snapshot: Path
    snapshot_manifest: dict[str, Any]
    files: dict[str, bytes]
    checks: tuple[str, ...]


def validate_revision(store: ArtifactStore, revision: int) -> RevisionValidation:
    snapshot = store.verify_revision(revision)
    manifest = strict_loads((snapshot / "snapshot-manifest.json").read_bytes())
    files = {
        item["path"]: (snapshot / item["path"]).read_bytes()
        for item in manifest["files"]
    }
    checks = ["snapshot_manifest"]
    # Preserve the current pack, Evidence Core, component, grade, and final
    # package validation bodies in their current order.
    return RevisionValidation(
        revision=revision,
        snapshot=snapshot,
        snapshot_manifest=dict(manifest),
        files=files,
        checks=tuple(checks),
    )
```

Make CLI `_validate` a response wrapper only:

```python
def _validate(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = validate_revision(_store_for(args), args.revision)
    return 0, response(
        command="validate",
        ok=True,
        code=0,
        message="revision valid",
        run_id=args.run_id,
        revision=args.revision,
        data={"validated": True, "checks": list(result.checks)},
    )
```

If Pack manifests or component runs exist, retain their conditional checks. Web export requires the four fixed checks and requires the conditional checks whenever corresponding artifacts exist.

- [ ] **Step 4: Verify no behavior drift**

Run:

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.trust.test_revision_validation tests.integration.test_cli_finalization_flow tests.unit.outputs.test_validation -v
```

Expected: PASS with the existing CLI check list unchanged.

- [ ] **Step 5: Commit the reusable validator**

```text
git add plugin/trusted-ceo-agent/trusted_ceo_agent/trust/revision_validation.py plugin/trusted-ceo-agent/trusted_ceo_agent/cli.py tests/unit/trust tests/integration/test_cli_finalization_flow.py
git commit -m "refactor: expose full revision validation"
```

## Task 6: Build the exact transitive evidence closure

**Files:**

- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/closure.py`
- Create: `tests/unit/web_report/__init__.py`
- Create: `tests/unit/web_report/test_closure.py`

- [ ] **Step 1: Write failing closure and broken-ref tests**

```python
def test_signal_and_derived_fact_close_to_observed_sources(self) -> None:
    closure = build_evidence_closure(final_result(), evidence_core())
    self.assertEqual(("evidence_main",), tuple(item["evidence_link_id"] for item in closure.evidence_links))
    self.assertEqual(("signal_main",), tuple(item["signal_id"] for item in closure.signals))
    self.assertEqual(
        ("fact_input", "fact_metric"),
        tuple(item["fact_id"] for item in closure.facts),
    )
    self.assertEqual(("source_main",), tuple(item["source_id"] for item in closure.sources))

def test_missing_fact_fails_instead_of_being_dropped(self) -> None:
    core = evidence_core()
    core["signal_register"][0]["input_fact_ids"] = ["fact_missing"]
    with self.assertRaisesRegex(IntegrityError, "fact_missing"):
        build_evidence_closure(final_result(), core)
```

- [ ] **Step 2: Run and verify RED**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.web_report.test_closure -v
```

Expected: FAIL because `closure.py` is missing.

- [ ] **Step 3: Implement a typed, sorted closure**

```python
@dataclass(frozen=True)
class EvidenceClosure:
    facts: tuple[dict[str, Any], ...]
    signals: tuple[dict[str, Any], ...]
    evidence_links: tuple[dict[str, Any], ...]
    sources: tuple[dict[str, Any], ...]
    data_quality: tuple[dict[str, Any], ...]
    capability_map: dict[str, Any]


def build_evidence_closure(
    final_result: Mapping[str, Any],
    core: Mapping[str, Any],
) -> EvidenceClosure:
    ...
```

Algorithm:

1. index each register with duplicate-ID rejection;
2. start from every delivered issue `evidence_link_ids`;
3. include each link's `evidence_ref`;
4. for a Signal, include every `input_fact_ids`;
5. for a calculated/aggregated Fact, recursively include every `derivation.input_fact_ids`;
6. include every Fact `source_refs.source_id`;
7. include every Fact quality ID and the full capability map;
8. reject unknown refs and derivation cycles;
9. return each collection sorted by its stable ID.

Do not include unrelated Facts or Sources. Do not create a new Fact, Signal, relation, or claim.

- [ ] **Step 4: Run closure and Evidence Core tests**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.web_report.test_closure tests.unit.evidence.test_evidence_builders -v
```

Expected: PASS.

- [ ] **Step 5: Commit evidence closure**

```text
git add plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/closure.py tests/unit/web_report
git commit -m "feat: derive web evidence closure"
```

## Task 7: Materialize access-policy-safe source previews

**Files:**

- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/previews.py`
- Create: `tests/unit/web_report/test_previews.py`
- Create: `tests/safety/test_web_report_boundaries.py`

- [ ] **Step 1: Write failing permitted/restricted/locator tests**

```python
def test_permitted_csv_preview_contains_only_selected_record_and_fields(self) -> None:
    result = build_source_views(snapshot, closure)
    preview = result.previews[0]
    self.assertEqual(["customer", "revenue"], preview["column_labels"])
    self.assertEqual([["A", "100"]], preview["rows"])
    self.assertNotIn("secret_note", json.dumps(preview, ensure_ascii=False))

def test_restricted_and_prohibited_sources_never_embed_values(self) -> None:
    for policy in ("restricted", "prohibited"):
        preview = build_source_views(snapshot, closure_with_policy(policy)).previews[0]
        self.assertEqual([], preview["column_labels"])
        self.assertEqual([], preview["rows"])
        self.assertEqual(policy, preview["masking_status"])

def test_source_blob_hash_and_extraction_hash_are_revalidated(self) -> None:
    with self.assertRaises(IntegrityError):
        build_source_views(tampered_snapshot, closure)
```

Cover `csv_records`, `json_pointer`, and `xlsx_cells` in separate tests. The XLSX case must prove formula cells are not exported as trusted values.

- [ ] **Step 2: Run and verify RED**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.web_report.test_previews tests.safety.test_web_report_boundaries -v
```

Expected: FAIL because preview construction is missing.

- [ ] **Step 3: Implement preview construction**

```python
@dataclass(frozen=True)
class SourceViews:
    sources: tuple[dict[str, Any], ...]
    previews: tuple[dict[str, Any], ...]


def build_source_views(
    snapshot_root: Path,
    closure: EvidenceClosure,
    *,
    max_preview_bytes: int = MAX_PREVIEW_BYTES,
) -> SourceViews:
    ...
```

For each unique `(source_id, extraction_hash)` Fact source reference:

1. resolve `snapshot_ref` with `ensure_within(snapshot_root, ...)`;
2. verify source byte length and SHA-256 before parsing;
3. select the existing adapter by trusted `media_type`;
4. find the exact locator and selected fields;
5. verify the existing `extraction_hash`;
6. normalize values to strings, booleans, or null without formulas or executable markup;
7. set `preview_ref = make_id("preview", {"source_id": ..., "extraction_hash": ...})`;
8. set `preview_hash = jcs_sha256(preview, omit_root_field="preview_hash")`;
9. sort previews by `preview_ref`;
10. enforce the 10 MiB total against JCS bytes.

When the next permitted preview would exceed the remaining budget, retain a metadata-only preview with:

```python
{
    "column_labels": [],
    "rows": [],
    "truncated": True,
    "truncation_reason": "bundle_preview_budget",
    "masking_status": "truncated",
}
```

Never read `sources/resolver.json`. Never include `original_path_token`, absolute path, raw workbook formula, or rows outside the source reference.

- [ ] **Step 4: Run preview and safety tests**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 5: Commit safe previews**

```text
git add plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/previews.py tests/unit/web_report/test_previews.py tests/safety/test_web_report_boundaries.py
git commit -m "feat: build bounded source previews"
```

## Task 8: Generate plugin-owned summary order and conservative charts

**Files:**

- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/presentation.py`
- Create: `tests/unit/web_report/test_presentation.py`

- [ ] **Step 1: Write failing order, no-ranking, and chart tests**

```python
def test_ceo_summary_is_grade_order_then_issue_id_and_never_more_than_three(self) -> None:
    manifest = build_presentation_manifest(result_with_five_issues(), closure())
    self.assertEqual(["issue_a", "issue_b", "issue_c"], manifest["ceo_summary_issue_refs"])
    self.assertEqual("grade_order_then_issue_id", manifest["selection_basis"])

def test_chart_requires_two_compatible_facts_and_keeps_evidence_refs(self) -> None:
    manifest = build_presentation_manifest(result(), two_period_closure())
    self.assertEqual(1, len(manifest["chart_specs"]))
    points = manifest["chart_specs"][0]["points"]
    self.assertEqual(["fact_p1", "fact_p2"], [item["value_ref"] for item in points])
    self.assertTrue(all(item["evidence_link_ids"] for item in points))

def test_incompatible_unit_or_scope_produces_no_chart(self) -> None:
    self.assertEqual([], build_presentation_manifest(result(), incompatible_closure())["chart_specs"])
```

- [ ] **Step 2: Run and verify RED**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.web_report.test_presentation -v
```

Expected: FAIL because `presentation.py` is missing.

- [ ] **Step 3: Implement deterministic presentation only**

```python
GRADE_ORDER = {
    "Decision Required": 0,
    "Immediate Verification": 1,
    "Expert Review Required": 2,
    "Monitor": 3,
    "Appendix Signal": 4,
    "Not Assessable": 5,
}

def build_presentation_manifest(
    final_result: Mapping[str, Any],
    closure: EvidenceClosure,
) -> dict[str, Any]:
    ...
```

Rules:

- select at most the first three issues sorted by `(GRADE_ORDER[primary_grade], issue_id)`;
- emit at most one metric card per selected issue using the first sorted Fact `value_ref`;
- group chart candidates only when `metric_code`, scope, unit, currency, and value type are identical and at least two distinct time contexts exist;
- sort candidate groups by `(metric_code, issue_ref)` and emit at most two charts for the CEO summary;
- use the Fact's canonical value string; do not calculate deltas, averages, forecasts, or ranks;
- every chart point carries existing Evidence Link IDs that reach its Fact;
- copy only delivered `cross_issue_relations` into `issue_graph`;
- provide Korean labels for every grade and view heading;
- validate the result with `presentation-manifest.schema.json`.

- [ ] **Step 4: Run presentation tests**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 5: Commit presentation instructions**

```text
git add plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/presentation.py tests/unit/web_report/test_presentation.py
git commit -m "feat: derive trusted report presentation"
```

## Task 9: Expand accepted expert packets without accepting expert replies

**Files:**

- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/expert_packets.py`
- Create: `tests/unit/web_report/test_expert_packets.py`

- [ ] **Step 1: Write failing accepted-routing and completeness tests**

```python
def test_packet_is_expanded_from_accepted_candidate_and_snapshot(self) -> None:
    packets = build_expert_packet_view(files(), final_result(), closure(), run_id=RUN_ID, revision=10)
    packet = packets[0]
    self.assertEqual("expert_packet_main", packet["expert_packet_id"])
    self.assertEqual(["fact_main"], packet["fact_refs"])
    self.assertEqual(["contracts"], packet["required_document_refs"])
    self.assertEqual(["source_main"], packet["source_refs"])
    self.assertEqual(
        jcs_sha256(packet, omit_root_field="packet_hash"),
        packet["packet_hash"],
    )

def test_unaccepted_candidate_and_unknown_ref_are_rejected(self) -> None:
    with self.assertRaises(IntegrityError):
        build_expert_packet_view(files_with_unaccepted_public_packet(), final_result(), closure(), run_id=RUN_ID, revision=10)
```

- [ ] **Step 2: Run and verify RED**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.web_report.test_expert_packets -v
```

Expected: FAIL because `expert_packets.py` is missing.

- [ ] **Step 3: Implement deterministic one-way packet expansion**

```python
def build_expert_packet_view(
    files: Mapping[str, bytes],
    final_result: Mapping[str, Any],
    closure: EvidenceClosure,
    *,
    run_id: str,
    revision: int,
) -> tuple[dict[str, Any], ...]:
    ...
```

Resolve each delivered `final_result.expert_review_packets` item back to:

- the accepted structured packet in `final/structured-output.json`;
- its target issue;
- matching integrated/deep expert candidate by target local key and trigger ref;
- candidate evidence proposals;
- required document refs;
- issue cause and counter-hypothesis refs;
- remaining uncertainties and blind spots;
- Fact/Evidence/Source refs and logical source locators.

Reject a public packet with no accepted structured candidate. Do not call a model. Do not invent a question. Do not add any expert response, status, upload, validation, or reanalysis field.

- [ ] **Step 4: Run packet and finalization tests**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.web_report.test_expert_packets tests.unit.outputs.test_runtime_finalization -v
```

Expected: PASS.

- [ ] **Step 5: Commit expert packet expansion**

```text
git add plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/expert_packets.py tests/unit/web_report/test_expert_packets.py
git commit -m "feat: export one-way expert packets"
```

## Task 10: Build ancestry, trust events, file manifest, and revision comparison

**Files:**

- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/revisions.py`
- Create: `tests/unit/web_report/test_revisions.py`

- [ ] **Step 1: Write failing ancestry and previous-final tests**

```python
def test_ancestry_hash_covers_every_manifest_in_order(self) -> None:
    view = build_revision_artifacts(store, current_revision=10)
    expected = jcs_sha256({
        "manifests": [
            {"revision": revision, "manifest_hash": manifest_hash}
            for revision, manifest_hash in EXPECTED_MANIFESTS
        ]
    })
    self.assertEqual(expected, view.revision_ancestry_hash)

def test_previous_final_is_nearest_ancestor_with_final_result(self) -> None:
    view = build_revision_artifacts(store_with_final_results_at(6, 10), current_revision=10)
    self.assertTrue(view.revision_view["available"])
    self.assertEqual(6, view.revision_view["base_revision"])
    self.assertEqual(10, view.revision_view["compare_revision"])

def test_no_previous_final_is_explicit_not_synthetic(self) -> None:
    view = build_revision_artifacts(store, current_revision=10)
    self.assertFalse(view.revision_view["available"])
    self.assertEqual("NO_PRIOR_FINAL_RESULT", view.revision_view["unavailable_reason"])
    self.assertEqual([], view.revision_view["changed_refs"])
```

- [ ] **Step 2: Run and verify RED**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.web_report.test_revisions -v
```

Expected: FAIL because `revisions.py` is missing.

- [ ] **Step 3: Implement immutable ancestry and diff**

```python
@dataclass(frozen=True)
class RevisionArtifacts:
    revision_ancestry_hash: str
    trust_events: tuple[dict[str, Any], ...]
    file_manifest: tuple[dict[str, Any], ...]
    revision_view: dict[str, Any]


def build_revision_artifacts(
    store: ArtifactStore,
    *,
    current_revision: int,
) -> RevisionArtifacts:
    ...
```

For revisions 1 through current:

- call `store.verify_revision`;
- require `manifest.revision == n` and `manifest.parent_revision == n - 1`;
- hash ordered `{revision, manifest_hash}` records with JCS;
- parse `audit/events/rNNNN-<command>.json`;
- use event order for `sequence`;
- set missing `timestamp` and `gate` to `null`;
- infer `actor_kind="human"` only for `approve-interactive` and `decide-interactive`, otherwise `runtime`;
- list approvals whose immutable record has `invalidated_by_revision == n`;
- use current snapshot manifest entries for `file_manifest`, excluding `snapshot-manifest.json`, the bundle container, and any web export path.

For the nearest earlier snapshot containing `final/result.json`, diff stable IDs and JCS hashes for issues, relations, responses, monitoring, blind spots, packets, Facts, Signals, Evidence Links, and Sources. Categories are:

```text
data
mapping
mission
scope
pack
component
evidence
grade
approval
wording
expert_packet
```

Only emit a category when corresponding immutable paths or object hashes changed. Never summarize a difference with a model.

- [ ] **Step 4: Run revision and artifact-store tests**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.web_report.test_revisions tests.unit.test_artifact_store tests.unit.workflow.test_approvals -v
```

Expected: PASS.

- [ ] **Step 5: Commit trust and revision derivation**

```text
git add plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/revisions.py tests/unit/web_report/test_revisions.py
git commit -m "feat: derive web trust and revision views"
```

## Task 11: Assemble a deterministic web report from a fully validated revision

**Files:**

- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/exporter.py`
- Create: `tests/unit/web_report/test_exporter.py`

- [ ] **Step 1: Write failing export precondition and determinism tests**

```python
def test_export_requires_finalized_state_and_all_required_checks(self) -> None:
    with self.assertRaisesRegex(IntegrityError, "finalized"):
        export_web_report(non_finalized_store, run_id=RUN_ID, revision=9)
    with self.assertRaisesRegex(IntegrityError, "grade_recomputation"):
        export_web_report(incomplete_store, run_id=RUN_ID, revision=10)

def test_same_revision_exports_byte_identically(self) -> None:
    first = export_web_report(store, run_id=RUN_ID, revision=10)
    second = export_web_report(store, run_id=RUN_ID, revision=10)
    self.assertEqual(first.payload, second.payload)
    self.assertEqual(first.bundle["bundle_hash"], second.bundle["bundle_hash"])
    self.assertEqual(jcs_bytes(first.bundle), first.payload)

def test_export_does_not_change_store_state_or_snapshot(self) -> None:
    before_state = store.state()
    before_manifest = store.verify_revision(10).joinpath("snapshot-manifest.json").read_bytes()
    export_web_report(store, run_id=RUN_ID, revision=10)
    self.assertEqual(before_state, store.state())
    self.assertEqual(before_manifest, store.verify_revision(10).joinpath("snapshot-manifest.json").read_bytes())
```

- [ ] **Step 2: Run and verify RED**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.web_report.test_exporter -v
```

Expected: FAIL because `exporter.py` is missing.

- [ ] **Step 3: Implement the side-effect-free exporter API**

```python
@dataclass(frozen=True)
class ExportedWebReport:
    bundle: dict[str, Any]
    payload: bytes
    checks: tuple[str, ...]


def export_web_report(
    store: ArtifactStore,
    *,
    run_id: str,
    revision: int,
) -> ExportedWebReport:
    validation = validate_revision(store, revision)
    ...
```

Preconditions:

1. `store.state().run_id == run_id`;
2. `workflow/state.json.state == "finalized"`;
3. workflow revision and requested revision match;
4. `final/result.json.run_summary` matches run and revision;
5. all `REQUIRED_WEB_REPORT_CHECKS` exist;
6. `pack_manifest_schema` is required when `packs/manifest.json` exists;
7. `component_run_recomputation` is required when component runs exist;
8. current Final approval and result package validate;
9. approval ancestry validates as described below.

Approval ancestry:

- find the current authorizing Final Approval Record through `current_approvals(files, gate="final")`;
- normalize its seven summary fields, filling absent optional fields with null/false only in the web DTO;
- parse `result_artifact_ref` as the approved revision;
- find the first snapshot containing that Approval Record and require it to match the approved revision;
- require the finalized revision to be its uninterrupted descendant;
- reject any later invalidation of that approval;
- require `interactive_tty` and `fixture_only != true` for `trusted_final`;
- allow `poc_fixture` only when the immutable final result says `fixture_only=true`;
- never label `test_fixture` as trusted.

Assembly order:

```python
validation
closure = build_evidence_closure(...)
source_views = build_source_views(...)
presentation = build_presentation_manifest(...)
expert_packets = build_expert_packet_view(...)
revision_artifacts = build_revision_artifacts(...)
receipt = build_receipt(...)
bundle_without_hash = {...}
bundle["bundle_hash"] = jcs_sha256(bundle, omit_root_field="bundle_hash")
validate_bundle_document(bundle)
payload = jcs_bytes(bundle)
```

Use:

```text
bundle_version "1.0.0"
canonicalization_version "rfc8785-jcs-1"
receipt_version "1.0.0"
validator_version trusted_ceo_agent.__version__
finalization_event_time null when no immutable finalization timestamp exists
final_result_hash SHA-256 of stored final/result.json bytes
snapshot_manifest_hash stored manifest_hash
```

Build `official_url_policy` from accepted `official_external` Sources only. Default to `allowed_schemes=["https"]`, `allowed_origins=[]`, `allow_redirects=false`. A Source metadata URL is included only when it is HTTPS, its exact origin is added, it has no credentials, and it contains no local path.

- [ ] **Step 4: Run exporter and existing output tests**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.web_report.test_exporter tests.unit.outputs.test_renderer tests.unit.outputs.test_validation tests.unit.outputs.test_runtime_finalization -v
```

Expected: PASS.

- [ ] **Step 5: Commit deterministic export**

```text
git add plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/exporter.py tests/unit/web_report/test_exporter.py
git commit -m "feat: export deterministic web reports"
```

## Task 12: Cross-validate a registered bundle and return a structured decision

**Files:**

- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/eligibility.py`
- Create: `tests/unit/web_report/test_eligibility.py`

- [ ] **Step 1: Write failing trusted, POC, and tamper decisions**

```python
def test_registered_tty_bundle_is_trusted(self) -> None:
    exported = export_web_report(store, run_id=RUN_ID, revision=10)
    decision = decide_viewer_eligibility(
        store,
        expected_run_id=RUN_ID,
        expected_revision=10,
        bundle_payload=exported.payload,
    )
    self.assertTrue(decision["eligible"])
    self.assertEqual("trusted_final", decision["viewer_mode"])
    self.assertEqual("승인·검증된 실행본", decision["badge_label_ko"])

def test_fixture_bundle_is_never_promoted_to_trusted(self) -> None:
    decision = decide_viewer_eligibility(poc_store, expected_run_id=RUN_ID, expected_revision=10, bundle_payload=poc_payload)
    self.assertEqual("poc_fixture", decision["viewer_mode"])
    self.assertEqual("검증된 POC 시연 실행본", decision["badge_label_ko"])

def test_schema_valid_rehashed_tamper_is_rejected_by_reexport(self) -> None:
    tampered = change_title_and_rehash(exported.bundle)
    decision = decide_viewer_eligibility(store, expected_run_id=RUN_ID, expected_revision=10, bundle_payload=jcs_bytes(tampered))
    self.assertFalse(decision["eligible"])
    self.assertEqual("BYTE_MISMATCH", decision["failure_code"])
```

- [ ] **Step 2: Run and verify RED**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.web_report.test_eligibility -v
```

Expected: FAIL because `eligibility.py` is missing.

- [ ] **Step 3: Implement fail-closed byte-equivalence validation**

```python
def decide_viewer_eligibility(
    store: ArtifactStore,
    *,
    expected_run_id: str,
    expected_revision: int,
    bundle_payload: bytes,
) -> dict[str, Any]:
    ...
```

Processing:

1. bounded parse and internal validation of supplied bytes;
2. expected run and revision comparison;
3. full `export_web_report` from the registered run;
4. exact supplied bytes equality to recomputed JCS payload;
5. bundle hash, receipt, snapshot manifest, result hash, ancestry hash, approval mode, and completed checks equality;
6. schema validation of the final decision.

Expected validation denials return a schema-valid decision rather than throwing away the reason:

```python
def denied(code: str, message: str, *, run_id: str | None, revision: int | None, bundle_hash: str | None) -> dict[str, Any]:
    decision = {
        "decision_version": "1.0.0",
        "eligible": False,
        "viewer_mode": "rejected",
        "badge_label_ko": "열 수 없는 묶음",
        "run_id": run_id,
        "revision": revision,
        "bundle_hash": bundle_hash,
        "completed_checks": [],
        "failure_code": code,
        "failure_message": message,
    }
    validate_eligibility_decision(decision)
    return decision
```

Unexpected filesystem or internal errors still propagate to the existing CLI boundary. Never return a trusted decision when full re-export cannot run.

- [ ] **Step 4: Run eligibility tests**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 5: Commit registered-run eligibility**

```text
git add plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/eligibility.py tests/unit/web_report/test_eligibility.py
git commit -m "feat: cross-validate registered web reports"
```

## Task 13: Expose read-only CLI commands and Skill parity

**Files:**

- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/cli.py`
- Modify: `plugin/trusted-ceo-agent/skills/trusted-ceo-agent/SKILL.md`
- Modify: `plugin/trusted-ceo-agent/skills/trusted-ceo-agent/references/workflow.md`
- Modify: `tests/plugin/test_cli_commands.py`
- Modify: `tests/plugin/test_skill_cli_parity.py`
- Create: `tests/integration/test_cli_web_report.py`

- [ ] **Step 1: Write failing parser and integration tests**

Add parser expectations:

```python
"export-web-report",
"validate-web-report",
```

Integration assertions:

```python
code, exported = call([
    "export-web-report",
    "--artifact-root", str(artifacts),
    "--run-id", run_id,
    "--revision", "10",
    "--output", str(bundle_path),
])
self.assertEqual(0, code, exported)
self.assertTrue(bundle_path.is_file())

code, decision = call([
    "validate-web-report",
    "--artifact-root", str(artifacts),
    "--run-id", run_id,
    "--revision", "10",
    "--bundle", str(bundle_path),
])
self.assertEqual(0, code, decision)
self.assertEqual("trusted_final", decision["data"]["viewer_eligibility"]["viewer_mode"])
```

Also assert both commands leave `state.json` and the revision manifest byte-identical.

- [ ] **Step 2: Run and verify RED**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.plugin.test_cli_commands tests.integration.test_cli_web_report -v
```

Expected: FAIL because the parser does not expose the commands.

- [ ] **Step 3: Add exact CLI arguments**

```python
export_web = commands.add_parser("export-web-report")
_add_run(export_web)
export_web.add_argument("--revision", type=int, required=True)
export_web.add_argument("--output", type=Path, required=True)

validate_web = commands.add_parser("validate-web-report")
_add_run(validate_web)
validate_web.add_argument("--revision", type=int, required=True)
validate_web.add_argument("--bundle", type=Path, required=True)
```

Handlers:

```python
def _export_web_report(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    store = _store_for(args)
    exported = export_web_report(store, run_id=args.run_id, revision=args.revision)
    run_dir = store.open_run(args.run_id).resolve(strict=True)
    destination = args.output.resolve(strict=False)
    if _is_relative_to(destination, run_dir):
        raise ContractError("web report output cannot be written inside the immutable run")
    atomic_write(destination, exported.payload)
    return 0, response(
        command="export-web-report",
        ok=True,
        code=0,
        message="web report exported",
        run_id=args.run_id,
        revision=args.revision,
        data={
            "output": str(destination),
            "bundle_hash": exported.bundle["bundle_hash"],
            "viewer_mode": exported.bundle["viewer_eligibility_receipt"]["claimed_viewer_mode"],
            "checks": list(exported.checks),
        },
    )


def _validate_web_report(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    _, payload = _stable_read(args.bundle.resolve(strict=True))
    decision = decide_viewer_eligibility(
        _store_for(args),
        expected_run_id=args.run_id,
        expected_revision=args.revision,
        bundle_payload=payload,
    )
    code = 0 if decision["eligible"] else EXIT_INTEGRITY
    return code, response(
        command="validate-web-report",
        ok=decision["eligible"],
        code=code,
        message="web report eligible" if decision["eligible"] else decision["failure_message"],
        run_id=args.run_id,
        revision=args.revision,
        data={"viewer_eligibility": decision},
    )
```

Do not expose `sources/resolver.json` or absolute output paths to the browser. The CLI response path is terminal-only; the web Route Handler must discard it.

- [ ] **Step 4: Update Skill and workflow reference**

Add after finalized `validate` and `render`:

```text
Use export-web-report --revision <current> --output <path> only after full validate succeeds.
Use validate-web-report --revision <current> --bundle <path> before a registered viewer trusts the bundle.
Both commands are read-only with respect to the immutable run. They never create approval.
```

Add both commands to the workflow reference's read-only list and exit-code behavior.

- [ ] **Step 5: Run parser, integration, Skill parity, and launcher tests**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.plugin.test_cli_commands tests.plugin.test_skill_cli_parity tests.plugin.test_launcher tests.integration.test_cli_web_report -v
```

Expected: PASS.

- [ ] **Step 6: Commit CLI and Skill integration**

```text
git add plugin/trusted-ceo-agent/trusted_ceo_agent/cli.py plugin/trusted-ceo-agent/skills/trusted-ceo-agent/SKILL.md plugin/trusted-ceo-agent/skills/trusted-ceo-agent/references/workflow.md tests/plugin/test_cli_commands.py tests/plugin/test_skill_cli_parity.py tests/integration/test_cli_web_report.py
git commit -m "feat: expose web report CLI commands"
```

## Task 14: Prove tamper resistance and failure isolation

**Files:**

- Modify: `tests/integration/test_cli_web_report.py`
- Modify: `tests/safety/test_web_report_boundaries.py`
- Create: `tests/determinism/test_web_report_export.py`

- [ ] **Step 1: Add red tests for every trust boundary**

Add one focused test per behavior:

```text
same revision export twice -> exact same bytes
wrong expected run ID -> RUN_ID_MISMATCH
wrong expected revision -> REVISION_MISMATCH
non-finalized run -> WORKFLOW_NOT_FINALIZED
missing grade recomputation artifact -> REQUIRED_CHECK_MISSING
fixture-only result -> POC mode, never trusted
changed title plus recomputed outer hash -> BYTE_MISMATCH
changed preview plus recomputed preview and bundle hashes -> BYTE_MISMATCH
broken Evidence Link -> REFERENCE_CLOSURE_BROKEN
absolute Windows path -> ABSOLUTE_PATH_LEAK
absolute POSIX path -> ABSOLUTE_PATH_LEAK
bundle over 50 MiB -> BUNDLE_SIZE_EXCEEDED before parse
output path inside immutable run -> contract error
restricted/prohibited preview with value -> schema or semantic rejection
unknown major -> schema rejection
failed new validation -> prior bundle file remains byte-identical
```

- [ ] **Step 2: Run and verify RED for newly uncovered cases**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.integration.test_cli_web_report tests.safety.test_web_report_boundaries tests.determinism.test_web_report_export -v
```

Expected: new cases fail for their named boundary, not for fixture setup errors.

- [ ] **Step 3: Make the smallest production fixes required by each failing test**

Do not weaken schemas or convert a rejection into a warning. Do not add fallback trust. Keep invalid bundle handling isolated from the last known-good bundle.

- [ ] **Step 4: Run the entire plugin suite**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest discover -s tests -v
```

Expected: all tests PASS with no warning or traceback.

- [ ] **Step 5: Commit security and determinism coverage**

```text
git add tests/integration/test_cli_web_report.py tests/safety/test_web_report_boundaries.py tests/determinism/test_web_report_export.py plugin/trusted-ceo-agent/trusted_ceo_agent/web_report plugin/trusted-ceo-agent/trusted_ceo_agent/cli.py
git commit -m "test: harden web report trust boundaries"
```

## Task 15: Produce and verify the actual-TTY representative golden bundle

**Files:**

- Create: `docs/runbooks/trusted-ceo-agent-actual-tty-golden-web-report.md`
- Create: `demo/web-report/golden/README.md`
- Create after actual terminal run: `demo/web-report/golden/web-report-bundle.json`
- Create after actual terminal run: `demo/web-report/golden/validation-decision.json`

This task has an automated precursor and a human-terminal acceptance. The automated integration test's `StringIO.isatty()` fixture does not satisfy the actual-terminal acceptance by itself.

- [ ] **Step 1: Write the runbook with fixed safe paths and commands**

Use:

```text
artifact root: artifacts/web-report-golden
mission: tests/fixtures/evaluation/normal_vertical/mission-contract.json
input: tests/fixtures/evaluation/normal_vertical/inputs/company.json
bundle: demo/web-report/golden/web-report-bundle.json
decision: demo/web-report/golden/validation-decision.json
```

The runbook instructs Codex to invoke `$trusted-ceo-agent`, follow all workflow gates, use fixed drafts only where the plugin creates a frozen Job, and stop for the user at every interactive approval. It explicitly prohibits copying an Approval Record from tests or calling the POC oracle.

- [ ] **Step 2: Run the representative workflow in the target Mac Codex session**

Use this exact user prompt in that Mac session:

```text
$trusted-ceo-agent를 사용해 tests/fixtures/evaluation/normal_vertical/mission-contract.json과 tests/fixtures/evaluation/normal_vertical/inputs/company.json을 분석하세요. artifact root는 artifacts/web-report-golden만 사용하세요. 모든 플러그인 명령은 frozen/offline/no-sync launcher로 실행하고, data·diagnostic·final 승인은 실제 터미널 TTY에서 내가 직접 수행할 때까지 멈추세요. POC oracle, fixture approval, 승인 파일 복사, 직접 Fact·Signal·등급 생성은 금지합니다. finalized revision이 생기면 full validate와 render까지만 수행하고 run ID와 revision을 알려주세요.
```

Expected: a `finalized` run with a current `interactive_tty` Final approval and no `fixture_only:true`.

- [ ] **Step 3: Export and cross-validate through the exact launcher**

Substitute only the actual run ID and finalized integer revision reported by the plugin:

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py validate --artifact-root artifacts/web-report-golden --run-id <actual-run-id> --revision <actual-revision>
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py export-web-report --artifact-root artifacts/web-report-golden --run-id <actual-run-id> --revision <actual-revision> --output demo/web-report/golden/web-report-bundle.json
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py validate-web-report --artifact-root artifacts/web-report-golden --run-id <actual-run-id> --revision <actual-revision> --bundle demo/web-report/golden/web-report-bundle.json
```

Expected:

```text
validate code 0 with snapshot_manifest, evidence_core, grade_recomputation, final_package
export-web-report code 0
validate-web-report code 0
viewer_mode trusted_final
badge_label_ko 승인·검증된 실행본
```

Capture only the final `validate-web-report` JSON response as `validation-decision.json`.

- [ ] **Step 4: Run privacy, schema, hash, and repeat-export checks**

```text
rg -n '(?:[A-Za-z]:[\\/]|file:|/Users/|/home/)' demo/web-report/golden
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.contracts.test_web_report_contract_semantics tests.determinism.test_web_report_export -v
```

Export the same revision to a temporary second path and compare bytes:

```text
Compare-Object (Get-Content -Raw -Encoding Byte demo/web-report/golden/web-report-bundle.json) (Get-Content -Raw -Encoding Byte $env:TEMP/web-report-bundle-second.json)
```

Expected: `rg` finds no local absolute path, tests PASS, and `Compare-Object` emits no difference.

- [ ] **Step 5: Document the portability boundary**

`demo/web-report/golden/README.md` states:

- the committed bundle is safe, deterministic viewer data;
- its full run is intentionally not committed because `sources/resolver.json` is server-only;
- on a different Mac it opens as `출처 미확인 묶음` until that Mac creates/registers its own full run;
- only a local successful `validate-web-report` may restore the trusted badge;
- the bundle is not evidence of expert review or expert reply.

- [ ] **Step 6: Commit only safe golden outputs**

```text
git add docs/runbooks/trusted-ceo-agent-actual-tty-golden-web-report.md demo/web-report/golden/README.md demo/web-report/golden/web-report-bundle.json demo/web-report/golden/validation-decision.json
git commit -m "test: add actual TTY web report golden"
```

Do not add `artifacts/web-report-golden`, source resolver files, `.env`, Codex credentials, or terminal transcripts.

## Task 16: Final cross-workstream verification

**Files:**

- No production files unless a failing test reveals a defect.

- [ ] **Step 1: Verify schemas, fixtures, and generated type drift**

```text
npm ci --prefix contracts/web-report
npm run generate:check --prefix contracts/web-report
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.contracts.test_web_report_contract_schemas tests.contracts.test_web_report_jcs tests.contracts.test_web_report_contract_semantics -v
```

Expected: PASS.

- [ ] **Step 2: Verify the entire Python suite**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest discover -s tests -v
```

Expected: PASS with no warning or traceback.

- [ ] **Step 3: Verify the production launcher**

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py --help
```

Expected: help contains `export-web-report` and `validate-web-report`.

- [ ] **Step 4: Verify the viewer's required imports**

```text
rg -n 'export (interface|type) (WebReportBundleV1|ViewerEligibilityDecisionV1|PresentationManifestV1|SourcePreviewV1|ExpertPacketViewItemV1|RevisionViewV1)' contracts/web-report/v1/generated/types.ts
```

Expected: all six viewer-facing names are present.

- [ ] **Step 5: Verify no placeholder or trust-bypass wording**

```text
rg -n -i 'TBD|FIXME|implement later|fake approval|auto.?approve|trust the receipt' contracts/web-report plugin/trusted-ceo-agent/trusted_ceo_agent/web_report docs/runbooks/trusted-ceo-agent-actual-tty-golden-web-report.md
```

Expected: no match.

- [ ] **Step 6: Inspect the staged boundary before the final integration commit**

```text
git status --short
git diff --check
git diff --stat
```

Expected: only intended Contract 0, plugin web-report, tests, runbook, and safe golden files are changed; `git diff --check` is clean.

## Acceptance checklist

- [ ] Six public Contract 0 schemas are closed Draft 2020-12 schemas.
- [ ] Every optional value is represented by a required nullable field.
- [ ] TypeScript is generated from schemas and drift fails CI.
- [ ] Valid trusted, POC, and unverified fixtures pass.
- [ ] Invalid hash, dangling reference, and synthesized oversize fixtures fail for the intended reason.
- [ ] Bundle and preview hashes use RFC 8785 JCS plus SHA-256.
- [ ] Existing engine snapshot canonicalization remains unchanged.
- [ ] Full revision validation is reused, not copied.
- [ ] Export requires `finalized`, required validation checks, current Final approval, and valid ancestry.
- [ ] Export is read-only and byte-deterministic for the same revision.
- [ ] CEO summary ordering and charts are plugin-owned and contain no new analytical judgment.
- [ ] Evidence, source preview, expert packet, trust, and revision refs are closed.
- [ ] Restricted and prohibited source values never enter the bundle.
- [ ] Registered validation independently re-exports and compares exact bytes.
- [ ] Fixture-only can never receive the trusted label.
- [ ] Independent JSON can only be `출처 미확인 묶음`.
- [ ] Failed validation cannot damage the immutable run or last known-good bundle.
- [ ] Actual-terminal Final approval, full validate, export, and cross-validation are demonstrated separately from simulated-TTY tests.
- [ ] No expert-reply intake or reanalysis field exists.
- [ ] All user-facing labels in the contract are Korean except technical IDs and file names.
