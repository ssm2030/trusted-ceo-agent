import copy
import unittest

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


SHA = "a" * 64
FACT_ID = "fact_" + "b" * 24
EVENT_ID = "event_" + "c" * 24


def event_fixture() -> dict:
    fields = {
        "party_roles": [FACT_ID],
        "rights": [],
        "obligations": [],
        "resource_and_control": [],
        "consideration": [],
        "conditions": [],
        "event_dates": [],
        "performance_state": [],
        "billing_state": [],
        "payment_state": [],
        "cancellation_state": [],
        "amounts": [],
        "incentives": [],
        "document_refs": [],
        "system_event_refs": [],
    }
    body = {
        "schema_version": "1.0.0",
        "event_id": EVENT_ID,
        "event_type": "contract_performance",
        "base_revision": 3,
        "evidence_core_ref": {
            "artifact_id": "artifact_" + "d" * 24,
            "artifact_hash": SHA,
            "payload_hash": SHA,
            "revision": 3,
        },
        **fields,
        "fact_refs": [FACT_ID],
        "source_lineage": [{
            "fact_ref": FACT_ID,
            "root_fact_refs": [FACT_ID],
            "sources": [{
                "source_id": "source_" + "e" * 24,
                "source_sha256": SHA,
                "lineage_set_refs": [f"lineage/sets/{SHA}.json"],
            }],
            "evidence_link_refs": [],
        }],
        "data_quality_refs": [],
        "materialization": {
            "producer": "deterministic_component",
            "input_hash": SHA,
        },
    }
    return {**body, "integrity": {"payload_hash": SHA}}


def route_fixture() -> dict:
    body = {
        "schema_version": "1.0.0",
        "route_id": "route_" + "f" * 24,
        "event_id": EVENT_ID,
        "base_revision": 3,
        "domain": "accounting",
        "screen_status": "triggered",
        "status": "deep_review_pending",
        "trigger_card_refs": [],
        "fact_refs": [FACT_ID],
        "signal_refs": [],
        "missing_capability_refs": [],
        "selected_pack_refs": ["accounting-core@1.0.0"],
        "selected_packs": [{
            "pack_ref": "accounting-core@1.0.0",
            "pack_sha256": SHA,
            "effective_authority": "boundary",
        }],
        "pack_manifest_hash": SHA,
        "effective_authority": "boundary",
        "required": True,
        "routing_reason_codes": ["mandatory_baseline"],
        "estimated_cost_class": "medium",
        "expert_role": "senior_accountant",
    }
    return {**body, "integrity": {"payload_hash": SHA}}


class EconomicEventDomainRouteSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schemas = SchemaStore()

    def test_closed_event_and_route_contracts_accept_valid_payloads(self) -> None:
        self.schemas.validate("economic-event.schema.json", event_fixture())
        self.schemas.validate("domain-route.schema.json", route_fixture())

    def test_contracts_reject_hidden_reasoning_and_new_judgment_fields(self) -> None:
        for field in ("hidden_reasoning", "grade", "approval", "conclusion"):
            with self.subTest(field=field):
                event = copy.deepcopy(event_fixture())
                event[field] = "forbidden"
                with self.assertRaises(ContractError):
                    self.schemas.validate("economic-event.schema.json", event)

                route = copy.deepcopy(route_fixture())
                route[field] = "forbidden"
                with self.assertRaises(ContractError):
                    self.schemas.validate("domain-route.schema.json", route)

    def test_route_status_and_authority_are_explicit_closed_enums(self) -> None:
        route = route_fixture()
        route["status"] = "selected_by_model"
        with self.assertRaises(ContractError):
            self.schemas.validate("domain-route.schema.json", route)

        route = route_fixture()
        route["effective_authority"] = "senior_grade"
        with self.assertRaises(ContractError):
            self.schemas.validate("domain-route.schema.json", route)

    def test_lineage_and_pack_hashes_are_mandatory(self) -> None:
        event = event_fixture()
        event["source_lineage"][0]["sources"][0].pop("source_sha256")
        with self.assertRaises(ContractError):
            self.schemas.validate("economic-event.schema.json", event)

        route = route_fixture()
        route["selected_packs"][0].pop("pack_sha256")
        with self.assertRaises(ContractError):
            self.schemas.validate("domain-route.schema.json", route)


if __name__ == "__main__":
    unittest.main()
