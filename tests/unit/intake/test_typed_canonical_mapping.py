import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.mapping import (
    ResolvedFieldMapping,
    build_canonical_mapping_proposal,
    resolve_confirmed_mappings,
)
from trusted_ceo_agent.intake.materialize import materialize_observed_facts
from trusted_ceo_agent.intake.models import ParsedDataset, ParsedRecord


def dataset(metric_code: str, value: str) -> ParsedDataset:
    return ParsedDataset(
        source_id="source_" + "d" * 24,
        media_type="application/json",
        fields=("as_of", metric_code),
        records=(ParsedRecord(
            1, "json_pointer", {"pointer": "/0"},
            {"as_of": "2026-04-30", metric_code: value},
        ),),
    )


def metric(code: str, data_type: str, unit_policy: str, origin: str = "raw_input") -> dict:
    return {
        "metric_code": code,
        "metric_origin": origin,
        "accepted_observation_roles": ["contract_event"],
        "data_type": data_type,
        "unit_policy": unit_policy,
        "time_role": "event_date",
        "allowed_dimensions": [],
    }


def resolve(source: ParsedDataset, definition: dict, unit_code, scale):
    proposal = build_canonical_mapping_proposal(source, [definition])
    question_ref = proposal["mappings"][0]["mapping_question_ref"]
    return resolve_confirmed_mappings(
        source,
        proposal,
        {"mapping": {
            "sources": {source.source_id: {"included": True}},
            "columns": {question_ref: {
                "observation_role": "contract_event",
                "unit_code": unit_code,
                "scale": scale,
                "time_role": "event_date",
                "dimension_code": None,
            }},
        }},
        [definition],
    )


class TypedCanonicalMappingTests(unittest.TestCase):
    def test_iso_date_metric_materializes_as_date_value(self) -> None:
        source = dataset("acceptance_date", "2026-04-15")
        definition = metric("acceptance_date", "date", "date")

        result = materialize_observed_facts(source, resolve(source, definition, None, None))

        self.assertEqual(1, len(result.fact_register))
        self.assertEqual((), result.data_quality_register)
        self.assertEqual({
            "value_type": "date",
            "canonical_value": "2026-04-15",
            "unit_code": None,
            "currency_code": None,
            "scale": None,
        }, result.fact_register[0]["value"])

    def test_invalid_date_is_blocking_quality_and_never_fact(self) -> None:
        source = dataset("acceptance_date", "2026-02-30")
        definition = metric("acceptance_date", "date", "date")

        result = materialize_observed_facts(source, resolve(source, definition, None, None))

        self.assertEqual((), result.fact_register)
        self.assertEqual("invalid_date", result.data_quality_register[0]["issue_code"])

    def test_wrong_unit_is_rejected_for_each_closed_policy(self) -> None:
        cases = (
            ("ratio", "percent"),
            ("hour", "hours"),
            ("percentage_point", "ratio"),
            ("count", None),
            ("single_currency_or_verified_conversion", "krw"),
        )
        for unit_policy, invalid_unit in cases:
            with self.subTest(unit_policy=unit_policy):
                source = dataset("metric", "1")
                definition = metric("metric", "decimal", unit_policy)
                with self.assertRaises(ContractError):
                    resolve(source, definition, invalid_unit, "1")

    def test_materializer_revalidates_forged_unit_mapping(self) -> None:
        source = dataset("gross_margin", "0.3")
        forged = ResolvedFieldMapping(
            mapping_question_ref="mappingquestion_" + "a" * 24,
            source_field_ref="sourcefield_" + "b" * 24,
            source_id=source.source_id,
            source_field="gross_margin",
            observation_role="contract_event",
            metric_code="gross_margin",
            data_type="decimal",
            unit_policy="ratio",
            unit_code="percent",
            scale="1",
            time_role="event_date",
            dimension_code=None,
            time_field="as_of",
            scope_fields=(),
        )
        with self.assertRaises(ContractError):
            materialize_observed_facts(source, [forged])

    def test_derived_output_is_not_proposed_for_intake_mapping(self) -> None:
        source = dataset("gross_margin_change_pp", "-2")
        definition = metric(
            "gross_margin_change_pp", "decimal", "percentage_point", "derived_output"
        )

        proposal = build_canonical_mapping_proposal(source, [definition])

        self.assertEqual([], proposal["mappings"])


if __name__ == "__main__":
    unittest.main()
