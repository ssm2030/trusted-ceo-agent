import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator, assemble_evidence_core
from trusted_ceo_agent.evidence.facts import build_calculated_fact, build_observed_fact
from trusted_ceo_agent.evidence.links import build_evidence_link
from trusted_ceo_agent.evidence.signals import build_signal
from trusted_ceo_agent.intake.document_evidence import build_document_evidence


SHA = "a" * 64
SOURCE_ID = "source_" + "a" * 24


def source_ref() -> dict:
    return {
        "source_id": SOURCE_ID,
        "observation_role": "ledger",
        "locator_type": "csv_records",
        "locator": {"record_indices": [1]},
        "selected_fields": ["revenue"],
        "record_count": 1,
        "filters": [],
        "group_by": [],
        "operation": "observe",
        "normalized_rows_hash": SHA,
        "row_multiset_hash": SHA,
        "lineage_set_ref": f"lineage/sets/{SHA}.json",
        "extraction_hash": SHA,
    }


class EvidenceBuilderTests(unittest.TestCase):
    @staticmethod
    def _document_core(
        source: dict,
        documents: list[dict],
        links: list[dict] | None = None,
    ) -> dict:
        return assemble_evidence_core(
            envelope={
                'schema_version': '1.0.0',
                'artifact_id': 'artifact_' + 'b' * 24,
                'run_id': 'run_20260721T000000Z_0123456789abcdef',
                'revision': 1,
                'parent_artifact_hash': None,
                'stage': 'evidence_ready',
                'created_at': '2026-07-21T00:00:00Z',
                'semantic_fingerprint': SHA,
                'artifact_hash': SHA,
            },
            mission_contract_ref='mission_' + 'c' * 24,
            pack_manifest={'pack_manifest_hash': SHA, 'pack_refs': []},
            component_manifest={'component_refs': []},
            source_registry=[source],
            data_quality_register=[],
            fact_register=[],
            signal_register=[],
            document_evidence_register=documents,
            evidence_links=links or [],
            capability_map={
                'capability_map_id': 'capability_map_' + 'd' * 24,
                'capabilities': [],
            },
        )

    def test_document_evidence_must_match_its_source_blob_and_be_unique(self) -> None:
        markdown = b'# Plan\nRevenue assumptions\n'
        digest = hashlib.sha256(markdown).hexdigest()
        source = {
            'source_id': 'source_' + digest[:24],
            'source_type': 'uploaded_file',
            'access_policy': 'permitted',
            'evidence_usage': 'primary',
            'observation_roles': [],
            'display_name': 'strategy/plan.md',
            'media_type': 'text/markdown',
            'sha256': digest,
            'size_bytes': len(markdown),
            'received_at': '2026-07-21T00:00:00Z',
            'snapshot_ref': f'sources/blobs/{digest}',
            'original_path_token': 'path_' + 'e' * 24,
            'aliases': [],
            'metadata': {},
        }
        documents = build_document_evidence(source, markdown.decode('utf-8'))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blob = root / source['snapshot_ref']
            blob.parent.mkdir(parents=True)
            blob.write_bytes(markdown)
            core = self._document_core(source, documents)
            EvidenceCoreValidator().validate(core, source_root=root)

            unknown = copy.deepcopy(documents)
            unknown[0]['source_id'] = 'source_' + 'f' * 24
            with self.assertRaises(IntegrityError):
                EvidenceCoreValidator().validate(
                    self._document_core(source, unknown), source_root=root,
                )

            changed_hash = copy.deepcopy(documents)
            changed_hash[0]['content_sha256'] = '0' * 64
            with self.assertRaises(IntegrityError):
                EvidenceCoreValidator().validate(
                    self._document_core(source, changed_hash), source_root=root,
                )

            changed_markdown = b'# Plan\nChanged assumptions\n'
            changed_digest = hashlib.sha256(changed_markdown).hexdigest()
            changed_source = {
                **source,
                'sha256': changed_digest,
                'size_bytes': len(changed_markdown),
                'snapshot_ref': f'sources/blobs/{changed_digest}',
            }
            changed_blob = root / changed_source['snapshot_ref']
            changed_blob.write_bytes(changed_markdown)
            with self.assertRaises(IntegrityError):
                EvidenceCoreValidator().validate(
                    self._document_core(changed_source, documents), source_root=root,
                )

            with self.assertRaises(IntegrityError):
                EvidenceCoreValidator().validate(
                    self._document_core(source, [documents[0], documents[0]]),
                    source_root=root,
                )

            missing_document_link = {
                'evidence_link_id': 'evidence_' + 'a' * 24,
                'target_ref': 'claim_' + 'b' * 24,
                'target_type': 'business_meaning',
                'evidence_ref': 'document_' + 'f' * 24,
                'evidence_kind': 'document',
                'polarity': 'supports',
                'role': 'corroboration',
                'rationale_template': 'The document corroborates this claim.',
                'value_refs': [],
                'stage': 'lens',
                'materialized_by': 'runtime_normalizer',
                'origin': {
                    'origin_type': 'model_proposal',
                    'origin_job_id': 'job_' + 'c' * 24,
                    'model_profile': 'balanced_structured',
                    'prompt_hash': SHA,
                    'proposal_hash': SHA,
                },
                'independence_group_id': 'independence_' + 'd' * 24,
            }
            with self.assertRaises(IntegrityError):
                EvidenceCoreValidator().validate(
                    self._document_core(
                        source,
                        documents,
                        [missing_document_link],
                    ),
                    source_root=root,
                )

    def test_observed_calculated_signal_and_link_are_deterministic(self) -> None:
        observed = build_observed_fact(
            fact_code="revenue.observed",
            metric_code="revenue",
            semantic_role="observation",
            observation_role="ledger",
            scope=[{"dimension_code": "business_unit", "member_code": "all"}],
            time_context={"period": "2026-01"},
            value={"value_type": "decimal", "canonical_value": "100", "unit_code": "currency", "currency_code": "KRW", "scale": "1"},
            source_refs=[source_ref()],
        )
        calculated = build_calculated_fact(
            fact_type="calculated",
            fact_code="revenue.change",
            metric_code="revenue_change",
            semantic_role="comparison",
            observation_role="derived",
            scope=observed["scope"],
            time_context=observed["time_context"],
            value={"value_type": "decimal", "canonical_value": "10", "unit_code": "percent", "currency_code": None, "scale": "1"},
            component_id="compare",
            component_version="1.0.0",
            operation_code="period_compare",
            formula_ref="compare.period.v1",
            parameter_hash=SHA,
            input_fact_ids=[observed["fact_id"]],
            component_run_id="component_run_" + "b" * 24,
        )
        signal = build_signal(
            signal_code="revenue.increase",
            rule_ref="rule.revenue.increase.v1",
            component_id="compare",
            component_version="1.0.0",
            component_run_id="component_run_" + "b" * 24,
            threshold_ref="threshold.revenue.increase",
            input_fact_ids=[calculated["fact_id"]],
            required_fact_codes=["revenue.change"],
            missing_fact_codes=[],
            scope=calculated["scope"],
            time_context=calculated["time_context"],
            evaluation={"operator": "gte", "actual": "10", "threshold": "5"},
            outcome="triggered",
            direction="up",
            impact_band_candidate="medium",
            urgency_band_candidate="routine",
        )
        link = build_evidence_link(
            target_ref="problem_candidate_" + "c" * 24,
            target_type="problem_candidate",
            evidence_ref=signal["signal_id"],
            evidence_kind="signal",
            evidence_outcome="triggered",
            polarity="supports",
            role="observation",
            rationale_template="Revenue changed by {value}",
            value_refs=[{"token": "value", "fact_or_signal_id": signal["signal_id"], "display_field": "evaluation.actual", "display_format_ref": "percent"}],
            stage="evidence_scan",
            materialized_by="runtime_normalizer",
            origin={"origin_type": "deterministic_rule", "origin_job_id": None, "model_profile": None, "prompt_hash": None, "proposal_hash": SHA},
            independence_group_id="independence_" + "d" * 24,
        )
        self.assertTrue(observed["fact_id"].startswith("fact_"))
        self.assertEqual([observed["fact_id"]], calculated["derivation"]["input_fact_ids"])
        self.assertEqual("deterministic_component", signal["producer"])
        self.assertTrue(link["evidence_link_id"].startswith("evidence_"))

    def test_unknown_values_and_invalid_not_assessable_signal_are_rejected(self) -> None:
        with self.assertRaises(ContractError):
            build_observed_fact(
                fact_code="bad", metric_code="bad", semantic_role="observation", observation_role="ledger",
                scope=[], time_context={"period": "2026-01"},
                value={"value_type": "string", "canonical_value": "n/a", "unit_code": None, "currency_code": None, "scale": None},
                source_refs=[source_ref()],
            )
        with self.assertRaises(ContractError):
            build_signal(
                signal_code="missing", rule_ref="r", component_id="ratio", component_version="1.0.0",
                component_run_id="component_run_" + "e" * 24, threshold_ref=None, input_fact_ids=[],
                required_fact_codes=["x"], missing_fact_codes=[], scope=[], time_context={"period": "2026-01"},
                evaluation={}, outcome="not_assessable",
            )

    def test_not_assessable_signal_cannot_support_problem(self) -> None:
        with self.assertRaises(ContractError):
            build_evidence_link(
                target_ref="problem_candidate_" + "c" * 24,
                target_type="problem_candidate",
                evidence_ref="signal_" + "d" * 24,
                evidence_kind="signal",
                evidence_outcome="not_assessable",
                polarity="supports",
                role="boundary",
                rationale_template="Missing data",
                value_refs=[], stage="lens", materialized_by="runtime_normalizer",
                origin={"origin_type": "model_proposal", "origin_job_id": "job_" + "e" * 24, "model_profile": "balanced", "prompt_hash": SHA, "proposal_hash": SHA},
                independence_group_id="independence_" + "f" * 24,
            )


if __name__ == "__main__":
    unittest.main()
