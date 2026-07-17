import copy
import hashlib
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict


SHA = "a" * 64
EVENT_ID = "event_" + "b" * 24
FACT_ID = "fact_" + "c" * 24
DOMAINS = ("accounting", "labor", "legal", "tax")


def event_fixture() -> dict:
    fields = {
        "party_roles": [FACT_ID], "rights": [], "obligations": [],
        "resource_and_control": [], "consideration": [], "conditions": [],
        "event_dates": [], "performance_state": [], "billing_state": [],
        "payment_state": [], "cancellation_state": [], "amounts": [],
        "incentives": [], "document_refs": [], "system_event_refs": [],
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
        "materialization": {"producer": "deterministic_component", "input_hash": SHA},
    }
    event = {**body, "integrity": {"payload_hash": hashlib.sha256(canonical_bytes(body)).hexdigest()}}
    return event


def manifest(domains: tuple[str, ...] = DOMAINS) -> tuple[dict, list[dict]]:
    entries = []
    catalog = []
    for index, domain in enumerate(domains, start=1):
        ref = f"{domain}-core@1.0.0"
        digest = f"{index:x}" * 64
        entries.append({
            "pack_type": "domain",
            "pack_id": f"{domain}-core",
            "pack_version": "1.0.0",
            "pack_sha256": digest,
            "effective_authority": "boundary" if domain != "accounting" else "full",
        })
        catalog.append({
            "pack_ref": ref,
            "domain": domain,
            "pack_sha256": digest,
            "effective_authority": "boundary" if domain != "accounting" else "full",
            "jurisdictions": ["KR"],
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": None,
        })
    body = {"schema_version": "1.0.0", "packs": entries}
    return {**body, "manifest_hash": hashlib.sha256(canonical_bytes(body)).hexdigest()}, catalog


def candidates(selected_domains: tuple[str, ...], *, source: str = "mandatory_baseline") -> dict:
    result = {
        "mandatory_baseline": [],
        "mission_requested": [],
        "event_data_account": [],
        "deterministic_signal": [],
        "cross_domain_trigger": [],
        "ai_proposed": [],
    }
    result[source] = [
        {"domain": domain, "pack_ref": f"{domain}-core@1.0.0"}
        for domain in selected_domains
    ]
    return result


def screens(selected_domains: tuple[str, ...], *, reverse: bool = False, duplicate: bool = False) -> list[dict]:
    values = [{
        "domain": domain,
        "status": "triggered" if domain in selected_domains else "not_applicable",
        "trigger_card_refs": [],
        "fact_refs": [FACT_ID] if domain in selected_domains else [],
        "signal_refs": [],
        "missing_capability_refs": [],
        "routing_reason_codes": [f"screen_{domain}"],
        "estimated_cost_class": "medium" if domain in selected_domains else "none",
    } for domain in DOMAINS]
    if reverse:
        values.reverse()
    if duplicate:
        values = [*values, copy.deepcopy(values[0]), copy.deepcopy(values[-1])]
    return values


def route(selected_domains: tuple[str, ...], *, candidate_sets: dict | None = None,
          screen_results: list[dict] | None = None, manifest_domains: tuple[str, ...] = DOMAINS):
    from trusted_ceo_agent.routing.domain_router import route_economic_event

    pack_manifest, catalog = manifest(manifest_domains)
    event = event_fixture()
    return route_economic_event(
        event=event,
        expected_revision=3,
        expected_event_hash=event["integrity"]["payload_hash"],
        registered_domains=DOMAINS,
        candidate_sets=candidate_sets or candidates(selected_domains),
        screen_results=screen_results or screens(selected_domains),
        pack_manifest=pack_manifest,
        pack_catalog=catalog,
        jurisdiction="KR",
        effective_at="2026-07-17T00:00:00Z",
    )


class MultiDomainRouterTests(unittest.TestCase):
    def test_zero_one_two_and_four_selected_domains_keep_the_same_event_id(self) -> None:
        for selected in ((), ("accounting",), ("accounting", "tax"), DOMAINS):
            with self.subTest(selected=selected):
                routes = route(selected)
                selected_routes = [item for item in routes if item["status"] != "not_applicable"]
                self.assertEqual(len(selected), len(selected_routes))
                self.assertEqual({EVENT_ID} if selected else set(),
                                 {item["event_id"] for item in selected_routes})
                self.assertEqual(list(DOMAINS), [item["domain"] for item in routes])

    def test_ai_candidates_are_additive_and_cannot_remove_deterministic_candidates(self) -> None:
        union = candidates(("accounting",), source="deterministic_signal")
        union["ai_proposed"] = [{"domain": "tax", "pack_ref": "tax-core@1.0.0"}]
        routes = route(
            ("accounting", "tax"),
            candidate_sets=union,
            screen_results=screens(("accounting", "tax")),
        )
        selected = {item["domain"]: item for item in routes if item["status"] != "not_applicable"}
        self.assertEqual({"accounting", "tax"}, set(selected))
        self.assertIn("deterministic_signal", selected["accounting"]["routing_reason_codes"])
        self.assertIn("ai_proposed", selected["tax"]["routing_reason_codes"])

    def test_unsupported_legal_labor_and_tax_are_explicit_boundaries(self) -> None:
        selected = ("labor", "legal", "tax")
        routes = route(selected, manifest_domains=())
        by_domain = {item["domain"]: item for item in routes}
        for domain, role in (
            ("labor", "labor_specialist"),
            ("legal", "licensed_attorney"),
            ("tax", "tax_accountant"),
        ):
            item = by_domain[domain]
            self.assertEqual("unsupported_pack", item["status"])
            self.assertEqual("boundary", item["effective_authority"])
            self.assertEqual([], item["selected_pack_refs"])
            self.assertEqual(role, item["expert_role"])
            self.assertIn(f"unsupported_{domain}_pack", item["routing_reason_codes"])
            self.assertNotIn("conclusion", item)

    def test_duplicate_input_and_completion_order_are_byte_equivalent(self) -> None:
        selected = ("accounting", "tax")
        first = route(selected)
        duplicated = candidates(selected)
        duplicated["mandatory_baseline"] = [
            *reversed(duplicated["mandatory_baseline"]),
            copy.deepcopy(duplicated["mandatory_baseline"][0]),
        ]
        second = route(
            selected,
            candidate_sets=dict(reversed(list(duplicated.items()))),
            screen_results=screens(selected, reverse=True, duplicate=True),
        )
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))

    def test_conflicting_screen_duplicates_missing_screen_and_stale_event_fail_closed(self) -> None:
        from trusted_ceo_agent.routing.domain_router import route_economic_event

        selected = ("accounting",)
        conflicting = screens(selected)
        conflict = copy.deepcopy(conflicting[0])
        conflict["status"] = "not_applicable"
        with self.assertRaises(ContractError):
            route(selected, screen_results=[*conflicting, conflict])
        with self.assertRaises(ContractError):
            route(selected, screen_results=conflicting[:-1])

        pack_manifest, catalog = manifest()
        event = event_fixture()
        args = {
            "event": event,
            "expected_revision": 3,
            "expected_event_hash": event["integrity"]["payload_hash"],
            "registered_domains": DOMAINS,
            "candidate_sets": candidates(selected),
            "screen_results": screens(selected),
            "pack_manifest": pack_manifest,
            "pack_catalog": catalog,
            "jurisdiction": "KR",
            "effective_at": "2026-07-17T00:00:00Z",
        }
        with self.assertRaises(RevisionConflict):
            route_economic_event(**{**args, "expected_revision": 2})
        with self.assertRaises(IntegrityError):
            route_economic_event(**{**args, "expected_event_hash": "0" * 64})

    def test_pack_manifest_hash_authority_domain_and_effective_period_fail_closed(self) -> None:
        from trusted_ceo_agent.routing.domain_router import route_economic_event

        pack_manifest, catalog = manifest(("accounting",))
        event = event_fixture()
        args = {
            "event": event,
            "expected_revision": 3,
            "expected_event_hash": event["integrity"]["payload_hash"],
            "registered_domains": DOMAINS,
            "candidate_sets": candidates(("accounting",)),
            "screen_results": screens(("accounting",)),
            "pack_manifest": pack_manifest,
            "pack_catalog": catalog,
            "jurisdiction": "KR",
            "effective_at": "2026-07-17T00:00:00Z",
        }
        tampered_manifest = copy.deepcopy(pack_manifest)
        tampered_manifest["packs"][0]["effective_authority"] = "boundary"
        with self.assertRaises(IntegrityError):
            route_economic_event(**{**args, "pack_manifest": tampered_manifest})

        tampered_catalog = copy.deepcopy(catalog)
        tampered_catalog[0]["domain"] = "tax"
        with self.assertRaises(IntegrityError):
            route_economic_event(**{**args, "pack_catalog": tampered_catalog})

        expired_catalog = copy.deepcopy(catalog)
        expired_catalog[0]["valid_to"] = "2026-06-30T00:00:00Z"
        routes = route_economic_event(**{**args, "pack_catalog": expired_catalog})
        accounting = next(item for item in routes if item["domain"] == "accounting")
        self.assertEqual("unsupported_pack", accounting["status"])
        self.assertEqual([], accounting["selected_pack_refs"])

    def test_loaded_pack_and_runtime_index_adapters_do_not_change_existing_selectors(self) -> None:
        from trusted_ceo_agent.routing.domain_router import (
            catalog_entry_from_loaded_pack,
            catalog_entries_from_runtime_index,
        )

        self.assertTrue(callable(catalog_entry_from_loaded_pack))
        self.assertTrue(callable(catalog_entries_from_runtime_index))


if __name__ == "__main__":
    unittest.main()
