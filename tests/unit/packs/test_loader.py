import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.packs import PackLoader, PackRegistry


ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = ROOT / "plugin" / "trusted-ceo-agent"


class PackLoaderTests(unittest.TestCase):
    def test_initial_pack_set_loads_but_unregistered_full_claims_stay_provisional(self) -> None:
        registry = PackRegistry.load(
            PLUGIN_ROOT / "trust" / "pack-registry.json",
            PLUGIN_ROOT / "schemas" / "pack-registry.schema.json",
        )
        loader = PackLoader(PLUGIN_ROOT / "packs", PLUGIN_ROOT / "schemas", registry)

        loaded = loader.load_installed()

        self.assertEqual(8, len(loaded))
        self.assertEqual([], registry.entries)
        self.assertTrue(all(pack.effective_authority == "provisional" for pack in loaded))
        self.assertEqual(
            {
                "trusted-ceo-default",
                "b2b-services",
                "generic-business-boundary",
                "profitability-erosion",
                "revenue-mix-quality",
                "customer-concentration",
                "delivery-capacity-overrun",
                "revenue-timing-control",
            },
            {pack.pack_id for pack in loaded},
        )

    def test_exact_hash_registry_entry_can_grant_declared_authority(self) -> None:
        source = PLUGIN_ROOT / "packs" / "mission" / "trusted-ceo-default" / "1.0.0" / "pack.json"
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack_path = root / "packs" / "mission" / "trusted-ceo-default" / "1.0.0" / "pack.json"
            pack_path.parent.mkdir(parents=True)
            pack_path.write_bytes(payload)
            registry_path = root / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "entries": [
                            {
                                "pack_sha256": digest,
                                "pack_id": "trusted-ceo-default",
                                "pack_version": "1.0.0",
                                "effective_authority": "full",
                                "approval_record_hash": "a" * 64,
                                "approved_by_role": "design_owner",
                                "approved_at": "2026-07-17T00:00:00Z",
                                "contract_test_manifest_hash": "b" * 64,
                                "valid_from": "2026-07-17T00:00:00Z",
                                "revoked_at": None,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            registry = PackRegistry.load(registry_path, PLUGIN_ROOT / "schemas" / "pack-registry.schema.json")
            loaded = PackLoader(root / "packs", PLUGIN_ROOT / "schemas", registry).load_path(pack_path)

            self.assertEqual("full", loaded.effective_authority)


if __name__ == "__main__":
    unittest.main()
