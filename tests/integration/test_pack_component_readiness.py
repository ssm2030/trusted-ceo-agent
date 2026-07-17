import hashlib
import json
import unittest
from pathlib import Path

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.components.plans import (
    inspect_pack_component_contracts,
    materialize_component_plan,
)


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugin" / "trusted-ceo-agent"


def installed_revision() -> tuple[dict[str, bytes], dict]:
    paths = [
        PLUGIN_ROOT / "packs" / "domain" / "b2b-services" / "1.0.0" / "pack.json",
        *sorted((PLUGIN_ROOT / "packs" / "problem").glob("*/1.0.0/pack.json")),
    ]
    files: dict[str, bytes] = {}
    entries = []
    refs = []
    for path in paths:
        document = json.loads(path.read_text("utf-8"))
        payload = canonical_bytes(document)
        digest = hashlib.sha256(payload).hexdigest()
        files[f"packs/snapshots/{digest}.json"] = payload
        entries.append({
            "pack_type": document["pack_type"],
            "pack_id": document["pack_id"],
            "pack_version": document["pack_version"],
            "pack_sha256": digest,
            "effective_authority": "provisional",
        })
        refs.append(f"{document['pack_id']}@{document['pack_version']}")
    entries.sort(key=lambda item: (item["pack_type"], item["pack_id"], item["pack_version"]))
    body = {"schema_version": "1.0.0", "packs": entries}
    manifest = {**body, "manifest_hash": hashlib.sha256(canonical_bytes(body)).hexdigest()}
    files["packs/manifest.json"] = canonical_bytes(manifest)
    core = {
        "pack_manifest": {
            "pack_manifest_hash": manifest["manifest_hash"],
            "pack_refs": sorted(refs),
        },
        "fact_register": [],
    }
    return files, core


class PackComponentReadinessTests(unittest.TestCase):
    def test_every_installed_problem_step_has_a_valid_component_contract(self) -> None:
        files, core = installed_revision()
        report = inspect_pack_component_contracts(files=files, core=core)
        self.assertEqual(17, len(report))
        self.assertEqual({"ready"}, {item["status"] for item in report})
        self.assertTrue(all(item["reason_code"] is None for item in report))

    def test_valid_installed_steps_fail_closed_when_no_facts_are_available(self) -> None:
        files, core = installed_revision()
        problem_refs = [
            "customer-concentration@1.0.0",
            "delivery-capacity-overrun@1.0.0",
            "profitability-erosion@1.0.0",
            "revenue-mix-quality@1.0.0",
            "revenue-timing-control@1.0.0",
        ]
        analysis = materialize_component_plan(
            files=files,
            core=core,
            stage="analysis",
            problem_family_refs=problem_refs,
        )
        issues = [{
            "local_key": f"issue_{index}",
            "payload": {"problem_family_ref": ref, "scope_key": f"scope-{index}"},
        } for index, ref in enumerate(problem_refs)]
        deep = materialize_component_plan(
            files=files,
            core=core,
            stage="deep_dive",
            integrated_assessment={"payload": {"integrated_issues": issues}},
            approved_scope={
                "issue_ids": [item["local_key"] for item in issues],
                "component_ids": [
                    "bridge_decompose", "flow_aging", "reconcile", "temporal_alignment",
                ],
            },
        )
        entries = [*analysis.entries, *deep.entries]
        self.assertEqual(17, len(entries))
        self.assertEqual({"not_assessable"}, {entry["status"] for entry in entries})
        self.assertTrue(all(entry["reason_codes"] == ["missing_input_fact"] for entry in entries))


if __name__ == "__main__":
    unittest.main()
