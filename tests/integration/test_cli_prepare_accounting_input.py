from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

from tests.support import confirmed_mission
from tests.support_accounting_multitable import valid_accounting_multitable_document
from trusted_ceo_agent import cli
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.runtime_components import normalize_authorized_scope
from trusted_ceo_agent.trust.artifact_store import ArtifactStore


ROOT = Path(__file__).resolve().parents[2]
REQUEST_KEYS = {
    "scope_ref",
    "suite",
    "tier_zero_input",
    "raw_core_population",
    "revenue_input",
    "cashflow_input",
    "project_cost_inputs",
}


def call(arguments: list[str]) -> tuple[int, dict[str, Any]]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(arguments)
    return code, json.loads(output.getvalue())


def payloads(snapshot: Path) -> dict[str, bytes]:
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    return {
        item["path"]: (snapshot / Path(item["path"])).read_bytes()
        for item in manifest["files"]
    }


def prepare_authorized_accounting_scope(
    root: Path,
    *,
    required_inputs: tuple[str, ...] = ("accounting",),
) -> dict[str, Any]:
    mission_path = root / "mission.json"
    source_path = root / "dataset.json"
    artifacts = root / "artifacts"
    mission_path.write_bytes(canonical_bytes(confirmed_mission()))
    source_path.write_bytes(canonical_bytes(valid_accounting_multitable_document()))

    code, started = call([
        "start",
        "--artifact-root", str(artifacts),
        "--mission-contract", str(mission_path),
        "--input", str(source_path),
    ])
    if code != 0:
        raise AssertionError(started)
    common = ["--artifact-root", str(artifacts), "--run-id", started["run_id"]]
    code, scanned = call(["scan", *common, "--expected-revision", "1"])
    if code != 0:
        raise AssertionError(scanned)

    store = ArtifactStore(artifacts)
    run_dir = store.open_run(started["run_id"])
    files = payloads(store.verify_revision(2))
    registry = json.loads(files["sources/registry.json"].decode("utf-8"))
    source = registry[0]
    scope = {
        "component_ids": ["bridge_decompose"],
        "issue_ids": ["issue_profitability"],
        "required_inputs": list(required_inputs),
    }
    normalized_scope = normalize_authorized_scope(scope)
    scope_ref = make_id("scope", normalized_scope)
    state = strict_loads(files["workflow/state.json"])
    state.update({"state": "deep_dive_authorized", "revision": 3})
    files["workflow/state.json"] = canonical_bytes(state)
    files["workflow/hitl-overlay.json"] = canonical_bytes({"deep_dive_scope": scope})
    files["reasoning/integrated-assessment.json"] = canonical_bytes({
        "payload": {
            "integrated_issues": [{
                "local_key": "issue_profitability",
                "payload": {
                    "problem_family_ref": "profitability_erosion",
                    "scope_key": "enterprise",
                },
            }],
        },
    })
    store.publish(2, files)
    return {
        "root": root,
        "artifacts": artifacts,
        "run_id": started["run_id"],
        "run_dir": run_dir,
        "store": store,
        "common": common,
        "revision": 3,
        "source_id": source["source_id"],
        "scope_ref": scope_ref,
    }


def publish_variant(
    context: dict[str, Any],
    mutate: Callable[[dict[str, bytes]], None],
) -> None:
    current = context["revision"]
    files = payloads(context["store"].verify_revision(current))
    mutate(files)
    state = strict_loads(files["workflow/state.json"])
    state["revision"] = current + 1
    files["workflow/state.json"] = canonical_bytes(state)
    context["store"].publish(current, files)
    context["revision"] = current + 1


def mutate_source(files: dict[str, bytes], **changes: Any) -> None:
    registry = json.loads(files["sources/registry.json"].decode("utf-8"))
    registry[0].update(changes)
    files["sources/registry.json"] = canonical_bytes(registry)


def command(
    context: dict[str, Any],
    output: Path,
    *,
    revision: int | None = None,
    source_id: str | None = None,
    scope_ref: str | None = None,
) -> list[str]:
    return [
        "prepare-accounting-input",
        *context["common"],
        "--revision", str(context["revision"] if revision is None else revision),
        "--source-id", context["source_id"] if source_id is None else source_id,
        "--scope-ref", context["scope_ref"] if scope_ref is None else scope_ref,
        "--output", str(output),
    ]


def unchanged_snapshot(context: dict[str, Any]) -> tuple[bytes, list[str], bytes]:
    revision = context["revision"]
    return (
        (context["run_dir"] / "state.json").read_bytes(),
        sorted(path.name for path in (context["run_dir"] / "snapshots").iterdir()),
        (context["store"].verify_revision(revision) / "snapshot-manifest.json").read_bytes(),
    )


class CliPrepareAccountingInputIntegrationTests(unittest.TestCase):
    def assert_failure_without_write(
        self,
        context: dict[str, Any],
        *,
        expected_code: int,
        output: Path | None = None,
        revision: int | None = None,
        source_id: str | None = None,
        scope_ref: str | None = None,
    ) -> dict[str, Any]:
        destination = output or context["root"] / "prepared-accounting.json"
        before = unchanged_snapshot(context)
        code, result = call(command(
            context,
            destination,
            revision=revision,
            source_id=source_id,
            scope_ref=scope_ref,
        ))
        self.assertEqual(expected_code, code, result)
        self.assertFalse(result["ok"], result)
        self.assertEqual(before, unchanged_snapshot(context))
        self.assertFalse(destination.exists())
        return result

    def test_prepares_canonical_handoff_without_mutating_revision_then_runs_components(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            context = prepare_authorized_accounting_scope(Path(directory))
            output = context["root"] / "prepared-accounting.json"
            before = unchanged_snapshot(context)

            code, result = call(command(context, output))

            self.assertEqual(0, code, result)
            self.assertEqual(context["revision"], result["revision"])
            self.assertEqual("deep_dive_authorized", result["state"])
            self.assertEqual(
                {
                    "source_id",
                    "source_sha256",
                    "scope_ref",
                    "target_revision",
                    "request_hash",
                },
                set(result["data"]),
            )
            self.assertEqual(4, result["data"]["target_revision"])
            self.assertEqual(before, unchanged_snapshot(context))

            request_bytes = output.read_bytes()
            request = strict_loads(request_bytes)
            self.assertEqual(request_bytes, canonical_bytes(json.loads(request_bytes)))
            self.assertEqual(REQUEST_KEYS, set(request))
            self.assertEqual(context["scope_ref"], request["scope_ref"])
            self.assertEqual(
                hashlib.sha256(request_bytes).hexdigest(),
                result["data"]["request_hash"],
            )

            code, executed = call([
                "run-components",
                *context["common"],
                "--scope-ref", context["scope_ref"],
                "--accounting-input", str(output),
                "--expected-revision", "3",
            ])
            self.assertEqual(0, code, executed)
            self.assertEqual(4, executed["revision"])
            self.assertEqual(64, executed["data"]["accounting_issue_family_count"])
            self.assertEqual(30, executed["data"]["accounting_result_artifact_count"])

    def test_rejects_stale_state_scope_requirement_and_registry_cardinality(self) -> None:
        cases = ("stale", "state", "scope", "requirement", "missing", "duplicate")
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                    context = prepare_authorized_accounting_scope(
                        Path(directory),
                        required_inputs=() if case == "requirement" else ("accounting",),
                    )
                    kwargs: dict[str, Any] = {"expected_code": 3}
                    if case == "stale":
                        kwargs.update(expected_code=6, revision=2)
                    elif case == "state":
                        def change_state(files: dict[str, bytes]) -> None:
                            state = strict_loads(files["workflow/state.json"])
                            state["state"] = "evidence_ready"
                            files["workflow/state.json"] = canonical_bytes(state)
                        publish_variant(context, change_state)
                    elif case == "scope":
                        kwargs["scope_ref"] = "scope_wrong"
                    elif case == "missing":
                        kwargs["source_id"] = "source_" + "b" * 24
                    elif case == "duplicate":
                        def duplicate(files: dict[str, bytes]) -> None:
                            registry = json.loads(files["sources/registry.json"].decode("utf-8"))
                            registry.append(copy.deepcopy(registry[0]))
                            files["sources/registry.json"] = canonical_bytes(registry)
                        publish_variant(context, duplicate)
                    self.assert_failure_without_write(context, **kwargs)

    def test_rejects_untrusted_or_invalid_source_registry_entry(self) -> None:
        cases = (
            {"access_policy": "restricted"},
            {"evidence_usage": "context_only"},
            {"unexpected": "field"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                    context = prepare_authorized_accounting_scope(Path(directory))
                    publish_variant(
                        context,
                        lambda files, value=changes: mutate_source(files, **value),
                    )
                    self.assert_failure_without_write(context, expected_code=3)

    def test_rejects_source_snapshot_binding_mismatches_as_integrity_errors(self) -> None:
        cases = ("source_id", "snapshot_ref", "size", "digest")
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                    context = prepare_authorized_accounting_scope(Path(directory))
                    selected_source = context["source_id"]
                    if case == "source_id":
                        selected_source = "source_" + "b" * 24
                        publish_variant(
                            context,
                            lambda files: mutate_source(files, source_id=selected_source),
                        )
                    elif case == "snapshot_ref":
                        publish_variant(
                            context,
                            lambda files: mutate_source(
                                files,
                                snapshot_ref="sources/blobs/" + "b" * 64,
                            ),
                        )
                    elif case == "size":
                        def wrong_size(files: dict[str, bytes]) -> None:
                            registry = json.loads(files["sources/registry.json"].decode("utf-8"))
                            size = int(registry[0]["size_bytes"])
                            registry[0]["size_bytes"] = size + 1
                            files["sources/registry.json"] = canonical_bytes(registry)
                        publish_variant(context, wrong_size)
                    else:
                        selected_source = "source_" + "b" * 24
                        def wrong_digest(files: dict[str, bytes]) -> None:
                            registry = json.loads(files["sources/registry.json"].decode("utf-8"))
                            original_ref = registry[0]["snapshot_ref"]
                            new_ref = "sources/blobs/" + "b" * 64
                            files[new_ref] = files[original_ref]
                            registry[0].update({
                                "source_id": selected_source,
                                "sha256": "b" * 64,
                                "snapshot_ref": new_ref,
                            })
                            files["sources/registry.json"] = canonical_bytes(registry)
                        publish_variant(context, wrong_digest)
                    self.assert_failure_without_write(
                        context,
                        expected_code=4,
                        source_id=selected_source,
                    )

    def test_rejects_existing_or_restricted_output_without_clobbering(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            context = prepare_authorized_accounting_scope(Path(directory))
            output = context["root"] / "existing.json"
            output.write_bytes(b"keep")
            before = unchanged_snapshot(context)

            code, result = call(command(context, output))

            self.assertEqual(3, code, result)
            self.assertEqual(b"keep", output.read_bytes())
            self.assertEqual(before, unchanged_snapshot(context))

        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            context = prepare_authorized_accounting_scope(Path(directory))
            output = context["run_dir"] / "forbidden.json"
            self.assert_failure_without_write(
                context,
                expected_code=3,
                output=output,
            )

    def test_rejects_symbolic_link_output_parent(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            context = prepare_authorized_accounting_scope(Path(directory))
            real_parent = context["root"] / "real-output"
            linked_parent = context["root"] / "linked-output"
            real_parent.mkdir()
            try:
                os.symlink(real_parent, linked_parent, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlink unavailable: {error}")
            self.assert_failure_without_write(
                context,
                expected_code=3,
                output=linked_parent / "prepared.json",
            )


if __name__ == "__main__":
    unittest.main()