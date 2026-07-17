import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.reasoning.normalizer import normalize_lens_draft


def job() -> dict:
    return {
        "job_id": "job_001",
        "stage": "lens",
        "artifact_ref": "artifact_001",
        "pack_manifest_hash": "b" * 64,
        "lens_id": "financial",
        "model_profile": "balanced_structured",
        "allowed_fact_ids": ["fact_margin", "fact_revenue"],
        "allowed_signal_ids": ["signal_margin"],
        "allowed_problem_family_refs": ["profitability-erosion"],
        "allowed_mechanism_refs": ["mix_shift", "timing"],
        "allowed_test_refs": ["test_mix"],
        "allowed_expert_trigger_refs": [],
        "required_signal_ids": ["signal_margin"],
    }


def valid_draft() -> dict:
    return {
        "assessment_status": "complete",
        "status_reason_codes": [],
        "observations": [{
            "local_key": "obs_margin",
            "statement_template": "Margin is {{margin_value}}.",
            "value_refs": [{"token": "margin_value", "fact_or_signal_id": "fact_margin", "display_field": "value", "display_format_ref": "percent"}],
            "fact_ids": ["fact_margin"],
            "signal_ids": ["signal_margin"],
        }],
        "business_meanings": [{
            "local_key": "meaning_margin",
            "observation_local_keys": ["obs_margin"],
            "statement_template": "Margin pressure is material.",
            "value_refs": [],
            "evidence_proposals": [{"evidence_ref": "fact_margin", "polarity": "supports", "role": "observation"}],
        }],
        "problem_candidates": [{
            "local_key": "problem_margin",
            "business_meaning_local_keys": ["meaning_margin"],
            "problem_family_ref": "profitability-erosion",
            "statement_template": "Profitability erosion requires review.",
            "value_refs": [],
            "evidence_proposals": [{"evidence_ref": "signal_margin", "polarity": "supports", "role": "observation"}],
        }],
        "cause_hypotheses": [{
            "local_key": "cause_mix",
            "problem_local_key": "problem_margin",
            "mechanism_ref": "mix_shift",
            "statement_template": "Mix may explain the pressure.",
            "value_refs": [],
            "evidence_proposals": [{"evidence_ref": "fact_revenue", "polarity": "supports", "role": "mechanism"}],
            "support_condition_refs": [],
            "rejection_condition_refs": [],
            "distinguishing_test_refs": ["test_mix"],
        }],
        "counter_hypotheses": [{
            "local_key": "counter_timing",
            "challenged_hypothesis_local_key": "cause_mix",
            "mechanism_ref": "timing",
            "statement_template": "Timing may be an alternative.",
            "value_refs": [],
            "evidence_proposals": [{"evidence_ref": "signal_margin", "polarity": "contradicts", "role": "counter_evidence"}],
        }],
        "challenge_reviews": [],
        "verification_tests": [],
        "signal_dispositions": [{
            "signal_id": "signal_margin",
            "disposition": "used_support",
            "target_local_keys": ["problem_margin"],
            "duplicate_of_signal_id": None,
            "context_evidence_ids": [],
            "rationale_template": "Used as support.",
        }],
        "uncertainties": [],
        "data_requests": [],
        "human_questions": [],
        "expert_trigger_candidates": [],
        "limitations": [],
    }


class LensNormalizerTests(unittest.TestCase):
    def test_runtime_derives_used_refs_and_materializes_evidence(self) -> None:
        card = normalize_lens_draft(job(), valid_draft())
        self.assertEqual(["fact_margin", "fact_revenue"], card["used_fact_ids"])
        self.assertEqual(["signal_margin"], card["used_signal_ids"])
        self.assertGreaterEqual(len(card["evidence_links"]), 4)
        self.assertTrue(all(link["materialized_by"] == "runtime_normalizer" for link in card["evidence_links"]))

    def test_allowlist_numeric_literal_and_missing_disposition_are_rejected(self) -> None:
        outside = valid_draft()
        outside["observations"][0]["fact_ids"] = ["fact_outside"]
        with self.assertRaises(ContractError):
            normalize_lens_draft(job(), outside)

        numeric = valid_draft()
        numeric["problem_candidates"][0]["statement_template"] = "Margin fell by 12%."
        with self.assertRaises(ContractError):
            normalize_lens_draft(job(), numeric)

        missing = valid_draft()
        missing["signal_dispositions"] = []
        with self.assertRaises(ContractError):
            normalize_lens_draft(job(), missing)

    def test_not_assessable_cannot_contain_problem_or_cause(self) -> None:
        draft = valid_draft()
        draft["assessment_status"] = "not_assessable"
        draft["data_requests"] = [{"local_key": "request_data", "statement_template": "Provide contract data."}]
        with self.assertRaises(ContractError):
            normalize_lens_draft(job(), draft)

    def test_nested_schema_and_pack_allowlists_are_enforced(self) -> None:
        wrong_nested_field = valid_draft()
        wrong_nested_field["data_requests"] = [{
            "local_key": "request_data",
            "question_template": "Provide contract data.",
        }]
        with self.assertRaises(ContractError):
            normalize_lens_draft(job(), wrong_nested_field)

        outside_family = valid_draft()
        outside_family["problem_candidates"][0]["problem_family_ref"] = "outside-family"
        with self.assertRaises(ContractError):
            normalize_lens_draft(job(), outside_family)

        outside_mechanism = valid_draft()
        outside_mechanism["cause_hypotheses"][0]["mechanism_ref"] = "outside-mechanism"
        with self.assertRaises(ContractError):
            normalize_lens_draft(job(), outside_mechanism)


if __name__ == "__main__":
    unittest.main()
