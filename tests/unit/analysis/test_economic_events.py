import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict
from trusted_ceo_agent.evidence.core import assemble_evidence_core
from trusted_ceo_agent.evidence.facts import build_observed_fact
from trusted_ceo_agent.evidence.links import build_evidence_link


SHA = "a" * 64
RUN_ID = "run_20260717T000000Z_0123456789abcdef"
SOURCE_ID = "source_" + "1" * 24


def source_reference(role: str, suffix: str) -> dict:
    digest = suffix * 64
    return {
        "source_id": SOURCE_ID,
        "observation_role": role,
        "locator_type": "csv_records",
        "locator": {"record_indices": [1]},
        "selected_fields": [role],
        "record_count": 1,
        "filters": [],
        "group_by": [],
        "operation": "observe",
        "normalized_rows_hash": digest,
        "row_multiset_hash": digest,
        "lineage_set_ref": f"lineage/sets/{digest}.json",
        "extraction_hash": digest,
    }


def source() -> dict:
    return {
        "source_id": SOURCE_ID,
        "source_type": "uploaded_file",
        "access_policy": "permitted",
        "evidence_usage": "primary",
        "observation_roles": ["contract_party", "contract_amount"],
        "display_name": "contracts.csv",
        "media_type": "text/csv",
        "sha256": "2" * 64,
        "size_bytes": 100,
        "received_at": "2026-07-17T00:00:00Z",
        "snapshot_ref": "sources/blobs/" + "2" * 64,
        "original_path_token": "path_" + "3" * 24,
        "aliases": [],
        "metadata": {},
    }


def observed_facts(*, amount_currency: str | None = "KRW", amount_unit: str | None = "currency",
                   amount_quality: tuple[str, ...] = ()) -> tuple[dict, dict]:
    party = build_observed_fact(
        fact_code="contract.party.customer",
        metric_code="party",
        semantic_role="event_party",
        observation_role="contract_party",
        scope=[],
        time_context={"as_of": "2026-07-17"},
        value={
            "value_type": "string",
            "canonical_value": "party_customer_001",
            "unit_code": None,
            "currency_code": None,
            "scale": None,
        },
        source_refs=[source_reference("contract_party", "4")],
    )
    amount = build_observed_fact(
        fact_code="contract.consideration.amount",
        metric_code="contract_amount",
        semantic_role="event_amount",
        observation_role="contract_amount",
        scope=[],
        time_context={"as_of": "2026-07-17"},
        value={
            "value_type": "decimal",
            "canonical_value": "1000000",
            "unit_code": amount_unit,
            "currency_code": amount_currency,
            "scale": "1",
        },
        source_refs=[source_reference("contract_amount", "5")],
        quality_issue_ids=amount_quality,
    )
    return party, amount


def quality(issue_id: str) -> dict:
    return {
        "quality_issue_id": issue_id,
        "source_ref": source_reference("contract_amount", "5"),
        "issue_code": "ambiguous_unit",
        "severity": "blocking",
        "affected_field": "amount",
        "raw_value_hash": "6" * 64,
        "normalized_role": "contract_amount",
        "reason_code": "amount_unit_ambiguous",
        "suggested_resolution": "Confirm the unit.",
        "resolution_status": "open",
    }


def core_fixture(*, facts: tuple[dict, ...] | None = None, quality_register: tuple[dict, ...] = ()) -> dict:
    if facts is None:
        facts = observed_facts()
    amount = next(item for item in facts if item["fact_code"] == "contract.consideration.amount")
    link = build_evidence_link(
        target_ref="business_meaning_" + "7" * 24,
        target_type="business_meaning",
        evidence_ref=amount["fact_id"],
        evidence_kind="fact",
        evidence_outcome=None,
        polarity="supports",
        role="observation",
        rationale_template="The event amount is linked to a source Fact.",
        value_refs=[],
        stage="economic_event",
        materialized_by="runtime_normalizer",
        origin={
            "origin_type": "deterministic_rule",
            "origin_job_id": None,
            "model_profile": None,
            "prompt_hash": None,
            "proposal_hash": "8" * 64,
        },
        independence_group_id="independence_" + "9" * 24,
    )
    return assemble_evidence_core(
        envelope={
            "schema_version": "1.0.0",
            "artifact_id": "artifact_" + "a" * 24,
            "run_id": RUN_ID,
            "revision": 3,
            "parent_artifact_hash": SHA,
            "stage": "evidence_core",
            "created_at": "2026-07-17T00:00:00Z",
            "semantic_fingerprint": SHA,
            "artifact_hash": "b" * 64,
        },
        mission_contract_ref="mission_" + "c" * 24,
        pack_manifest={"pack_manifest_hash": "d" * 64, "pack_refs": []},
        component_manifest={"component_refs": []},
        source_registry=[source()],
        data_quality_register=list(quality_register),
        fact_register=list(facts),
        signal_register=[],
        evidence_links=[link],
        capability_map={
            "capability_map_id": "capability_map_" + "e" * 24,
            "capabilities": [],
        },
    )


def bindings(party_id: str, amount_id: str) -> dict:
    return {
        "party_roles": [party_id],
        "rights": [],
        "obligations": [],
        "resource_and_control": [],
        "consideration": [amount_id],
        "conditions": [],
        "event_dates": [],
        "performance_state": [],
        "billing_state": [],
        "payment_state": [],
        "cancellation_state": [],
        "amounts": [amount_id],
        "incentives": [],
        "document_refs": [],
        "system_event_refs": [],
    }


def bound_facts(core: dict) -> tuple[dict, dict]:
    by_code = {item["fact_code"]: item for item in core["fact_register"]}
    return by_code["contract.party.customer"], by_code["contract.consideration.amount"]


class EconomicEventMaterializationTests(unittest.TestCase):
    def test_materialization_is_fact_only_deterministic_and_preserves_lineage(self) -> None:
        from trusted_ceo_agent.analysis.economic_events import materialize_economic_event

        core = core_fixture()
        party, amount = bound_facts(core)
        first = materialize_economic_event(
            evidence_core=core,
            expected_revision=3,
            expected_artifact_hash="b" * 64,
            event_type="contract_performance",
            field_fact_refs=bindings(party["fact_id"], amount["fact_id"]),
        )
        duplicate_bindings = bindings(party["fact_id"], amount["fact_id"])
        duplicate_bindings["amounts"] = [amount["fact_id"], amount["fact_id"]]
        second = materialize_economic_event(
            evidence_core=core,
            expected_revision=3,
            expected_artifact_hash="b" * 64,
            event_type="contract_performance",
            field_fact_refs=dict(reversed(list(duplicate_bindings.items()))),
        )

        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        self.assertEqual(sorted({party["fact_id"], amount["fact_id"]}), first["fact_refs"])
        amount_lineage = next(
            item for item in first["source_lineage"] if item["fact_ref"] == amount["fact_id"]
        )
        self.assertEqual([SOURCE_ID], [item["source_id"] for item in amount_lineage["sources"]])
        self.assertEqual(1, len(amount_lineage["evidence_link_refs"]))
        self.assertTrue(amount_lineage["evidence_link_refs"][0].startswith("evidence_"))
        self.assertNotIn("conclusion", first)
        self.assertNotIn("grade", first)
        self.assertNotIn("approval", first)

    def test_stale_revision_artifact_or_tampered_core_fails_closed(self) -> None:
        from trusted_ceo_agent.analysis.economic_events import materialize_economic_event

        core = core_fixture()
        party, amount = bound_facts(core)
        args = {
            "evidence_core": core,
            "expected_revision": 3,
            "expected_artifact_hash": "b" * 64,
            "event_type": "contract_performance",
            "field_fact_refs": bindings(party["fact_id"], amount["fact_id"]),
        }
        with self.assertRaises(RevisionConflict):
            materialize_economic_event(**{**args, "expected_revision": 2})
        with self.assertRaises(IntegrityError):
            materialize_economic_event(**{**args, "expected_artifact_hash": "0" * 64})

        tampered = copy.deepcopy(core)
        tampered["fact_register"][0]["value"]["canonical_value"] = "tampered"
        with self.assertRaises(IntegrityError):
            materialize_economic_event(**{**args, "evidence_core": tampered})

    def test_unknown_fact_prohibited_source_and_missing_lineage_fail_closed(self) -> None:
        from trusted_ceo_agent.analysis.economic_events import materialize_economic_event

        core = core_fixture()
        party, amount = bound_facts(core)
        base = {
            "evidence_core": core,
            "expected_revision": 3,
            "expected_artifact_hash": "b" * 64,
            "event_type": "contract_performance",
        }
        bad = bindings(party["fact_id"], amount["fact_id"])
        bad["rights"] = ["fact_" + "0" * 24]
        with self.assertRaises(ContractError):
            materialize_economic_event(**base, field_fact_refs=bad)

        prohibited = copy.deepcopy(core)
        prohibited["source_registry"][0]["access_policy"] = "prohibited"
        prohibited["integrity"]["payload_hash"] = __import__("hashlib").sha256(
            canonical_bytes({key: value for key, value in prohibited.items() if key != "integrity"})
        ).hexdigest()
        with self.assertRaises(ContractError):
            materialize_economic_event(
                **{**base, "evidence_core": prohibited},
                field_fact_refs=bindings(party["fact_id"], amount["fact_id"]),
            )

    def test_amount_unit_currency_and_blocking_quality_fail_closed(self) -> None:
        from trusted_ceo_agent.analysis.economic_events import materialize_economic_event

        for unit, currency in ((None, "KRW"), ("currency", None)):
            with self.subTest(unit=unit, currency=currency):
                facts = observed_facts(amount_unit=unit, amount_currency=currency)
                core = core_fixture(facts=facts)
                party, amount = bound_facts(core)
                with self.assertRaises(ContractError):
                    materialize_economic_event(
                        evidence_core=core,
                        expected_revision=3,
                        expected_artifact_hash="b" * 64,
                        event_type="contract_performance",
                        field_fact_refs=bindings(party["fact_id"], amount["fact_id"]),
                    )

        issue_id = "quality_" + "f" * 24
        facts = observed_facts(amount_quality=(issue_id,))
        core = core_fixture(facts=facts, quality_register=(quality(issue_id),))
        party, amount = bound_facts(core)
        with self.assertRaises(ContractError):
            materialize_economic_event(
                evidence_core=core,
                expected_revision=3,
                expected_artifact_hash="b" * 64,
                event_type="contract_performance",
                field_fact_refs=bindings(party["fact_id"], amount["fact_id"]),
            )


if __name__ == "__main__":
    unittest.main()
