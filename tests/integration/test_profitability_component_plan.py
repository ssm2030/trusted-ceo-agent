import hashlib
import json
import unittest
from pathlib import Path

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.components.plans import execute_materialized_plan, materialize_component_plan


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugin" / "trusted-ceo-agent"


def fact(identifier: str, code: str, value: str, *, period: str, unit: str) -> dict:
    return {
        "fact_id": identifier,
        "fact_code": code,
        "observation_role": "calculated" if code == "margin_driver_contribution_pp" else "ledger",
        "scope": [{"dimension_code": "portfolio", "member_code": "portfolio-a"}],
        "time_context": {"period": period},
        "value": {"value_type": "decimal", "canonical_value": value, "unit_code": unit},
    }


def revision_files(problem: dict, domain: dict) -> tuple[dict[str, bytes], dict]:
    files: dict[str, bytes] = {}
    entries = []
    for document in (domain, problem):
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
    entries.sort(key=lambda item: (item["pack_type"], item["pack_id"], item["pack_version"]))
    body = {"schema_version": "1.0.0", "packs": entries}
    manifest = {**body, "manifest_hash": hashlib.sha256(canonical_bytes(body)).hexdigest()}
    files["packs/manifest.json"] = canonical_bytes(manifest)
    return files, manifest


class ProfitabilityComponentPlanIntegrationTests(unittest.TestCase):
    def test_installed_profitability_pack_runs_analysis_and_approved_bridge(self) -> None:
        domain = json.loads((
            PLUGIN_ROOT / "packs" / "domain" / "b2b-services" / "1.0.0" / "pack.json"
        ).read_text("utf-8"))
        problem = json.loads((
            PLUGIN_ROOT / "packs" / "problem" / "profitability-erosion" / "1.0.0" / "pack.json"
        ).read_text("utf-8"))
        files, manifest = revision_files(problem, domain)
        pack_manifest = {
            "pack_manifest_hash": manifest["manifest_hash"],
            "pack_refs": ["b2b-services@1.0.0", "profitability-erosion@1.0.0"],
        }
        margin_facts = [
            fact("fact_" + "1" * 24, "gross_margin", "0.33", period="2026-01", unit="ratio"),
            fact("fact_" + "2" * 24, "gross_margin", "0.31", period="2026-02", unit="ratio"),
            fact("fact_" + "3" * 24, "gross_margin", "0.27", period="2026-03", unit="ratio"),
        ]
        core = {
            "envelope": {"artifact_hash": "a" * 64},
            "pack_manifest": pack_manifest,
            "fact_register": margin_facts,
        }

        analysis = materialize_component_plan(
            files=files,
            core=core,
            stage="analysis",
            problem_family_refs=["profitability-erosion@1.0.0"],
        )
        self.assertEqual(["ready", "ready"], [entry["status"] for entry in analysis.entries])
        analysis_runs = execute_materialized_plan(
            analysis, margin_facts, input_artifact_hash="a" * 64, max_workers=4,
        )
        self.assertEqual(["completed", "completed"], sorted(run.status for run in analysis_runs))
        calculated = [item for run in analysis_runs for item in run.output_facts]
        signals = [item for run in analysis_runs for item in run.output_signals]
        self.assertEqual("-4", calculated[0]["value"]["canonical_value"])
        self.assertEqual("percentage_point", calculated[0]["value"]["unit_code"])
        self.assertEqual("triggered", signals[0]["outcome"])
        self.assertEqual("trend_minimum_observations", signals[0]["threshold_ref"])

        drivers = [
            fact("fact_" + "4" * 24, "margin_driver_contribution_pp", "-2", period="2026-03", unit="percentage_point"),
            fact("fact_" + "5" * 24, "margin_driver_contribution_pp", "-1.2", period="2026-03", unit="percentage_point"),
        ]
        deep_facts = [*margin_facts, *calculated, *drivers]
        deep_core = {**core, "fact_register": deep_facts}
        deep = materialize_component_plan(
            files=files,
            core=deep_core,
            stage="deep_dive",
            integrated_assessment={"payload": {"integrated_issues": [{
                "local_key": "issue_profitability",
                "payload": {
                    "problem_family_ref": "profitability-erosion@1.0.0",
                    "scope_key": "portfolio-a",
                },
            }]}},
            approved_scope={
                "issue_ids": ["issue_profitability"],
                "component_ids": ["bridge_decompose"],
            },
        )
        self.assertEqual("ready", deep.entries[0]["status"])
        deep_runs = execute_materialized_plan(deep, deep_facts, input_artifact_hash="b" * 64)
        self.assertEqual("completed", deep_runs[0].status)
        self.assertEqual("-0.8", deep_runs[0].output_facts[0]["value"]["canonical_value"])
        self.assertNotIn("fact_" + "1" * 24, deep_runs[0].sorted_input_fact_ids)


if __name__ == "__main__":
    unittest.main()
