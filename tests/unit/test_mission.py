import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.mission import (
    is_confirmed_mission,
    materialize_confirmed_mission,
    mission_contract_hash,
    validate_confirmed_mission,
)
from tests.support import confirmed_mission, mission_body


class MissionContractTests(unittest.TestCase):
    def test_valid_confirmed_contract_is_accepted(self) -> None:
        mission = confirmed_mission()
        self.assertTrue(is_confirmed_mission(mission))
        self.assertEqual(mission["confirmation"]["contract_hash"], mission_contract_hash(mission))
        validate_confirmed_mission(mission)

    def test_legacy_top_level_flag_cannot_confirm_mission(self) -> None:
        self.assertFalse(is_confirmed_mission({"confirmed": True}))

    def test_confirmation_hash_must_cover_contract_body(self) -> None:
        mission = confirmed_mission()
        mission["business_question"] = "Changed after approval"
        with self.assertRaises(ContractError):
            validate_confirmed_mission(mission)

    def test_context_overlay_materializes_a_schema_valid_confirmed_contract(self) -> None:
        mission = materialize_confirmed_mission(
            mission_body(),
            {"mission_contract": {"business_question": "Approved question"}},
            actor_id="ceo-2",
            actor_role="ceo",
            confirmed_at="2026-07-17T01:00:00Z",
        )
        self.assertEqual("Approved question", mission["business_question"])
        self.assertEqual("ceo-2", mission["confirmation"]["actor_id"])
        validate_confirmed_mission(mission)

    def test_context_overlay_cannot_modify_non_allowlisted_contract_fields(self) -> None:
        with self.assertRaises(ContractError):
            materialize_confirmed_mission(
                mission_body(),
                {"mission_contract": {"business_model": "regulated_bank"}},
                actor_id="ceo-2",
                actor_role="ceo",
                confirmed_at="2026-07-17T01:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
