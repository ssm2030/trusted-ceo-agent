from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from trusted_ceo_agent.service.settings import ServiceSettings


class ServiceSettingsTests(unittest.TestCase):
    def test_defaults_bind_only_to_ipv4_loopback_and_use_approved_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "TRUSTED_CEO_INTERNAL_TOKEN": "t" * 43,
                "TRUSTED_CEO_SERVICE_ROOT": directory,
            }
            with patch.dict(os.environ, environment, clear=True):
                settings = ServiceSettings.from_environment()

        self.assertEqual("127.0.0.1", settings.host)
        self.assertEqual(8765, settings.port)
        self.assertEqual("gpt-5.6", settings.model)
        self.assertFalse(settings.ai_ready)

    def test_openai_key_marks_ai_ready_without_exposing_a_second_state_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "OPENAI_API_KEY": "test-key",
                "TRUSTED_CEO_INTERNAL_TOKEN": "t" * 43,
                "TRUSTED_CEO_SERVICE_ROOT": directory,
            }
            with patch.dict(os.environ, environment, clear=True):
                settings = ServiceSettings.from_environment()

        self.assertEqual("test-key", settings.openai_api_key)
        self.assertTrue(settings.ai_ready)

    def test_secrets_are_redacted_from_settings_repr(self) -> None:
        internal_token = "internal-token_" + "a" * 32
        openai_key = "test-openai-key"
        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "OPENAI_API_KEY": openai_key,
                "TRUSTED_CEO_INTERNAL_TOKEN": internal_token,
                "TRUSTED_CEO_SERVICE_ROOT": directory,
            }
            with patch.dict(os.environ, environment, clear=True):
                settings = ServiceSettings.from_environment()

        rendered = repr(settings)
        self.assertNotIn(internal_token, rendered)
        self.assertNotIn(openai_key, rendered)

    def test_non_loopback_host_and_invalid_token_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            invalid_settings = (
                ("0.0.0.0", "t" * 43),
                ("127.0.0.1", "short"),
                ("127.0.0.1", "한" * 32),
                ("127.0.0.1", ""),
                ("127.0.0.1", " " * 32),
                ("127.0.0.1", "a" * 31 + "\n"),
                ("127.0.0.1", "a" * 31 + "+"),
            )
            for host, token in invalid_settings:
                environment = {
                    "TRUSTED_CEO_SERVICE_HOST": host,
                    "TRUSTED_CEO_INTERNAL_TOKEN": token,
                    "TRUSTED_CEO_SERVICE_ROOT": directory,
                }
                with self.subTest(host=host, token_length=len(token)):
                    with patch.dict(os.environ, environment, clear=True):
                        with self.assertRaises(ValueError):
                            ServiceSettings.from_environment()

    def test_openai_key_with_whitespace_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for openai_key in (" ", " test-key", "test-key ", "test\nkey"):
                environment = {
                    "OPENAI_API_KEY": openai_key,
                    "TRUSTED_CEO_INTERNAL_TOKEN": "t" * 43,
                    "TRUSTED_CEO_SERVICE_ROOT": directory,
                }
                with self.subTest(openai_key=repr(openai_key)):
                    with patch.dict(os.environ, environment, clear=True):
                        with self.assertRaises(ValueError):
                            ServiceSettings.from_environment()

    def test_port_must_be_an_integer_in_the_tcp_port_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for port in ("0", "65536", "not-a-port"):
                environment = {
                    "TRUSTED_CEO_INTERNAL_TOKEN": "t" * 43,
                    "TRUSTED_CEO_SERVICE_PORT": port,
                    "TRUSTED_CEO_SERVICE_ROOT": directory,
                }
                with self.subTest(port=port):
                    with patch.dict(os.environ, environment, clear=True):
                        with self.assertRaises(ValueError):
                            ServiceSettings.from_environment()

    def test_service_root_is_absolute_and_settings_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "child" / ".."
            environment = {
                "TRUSTED_CEO_INTERNAL_TOKEN": "t" * 43,
                "TRUSTED_CEO_SERVICE_ROOT": os.fspath(root),
            }
            with patch.dict(os.environ, environment, clear=True):
                settings = ServiceSettings.from_environment()

        self.assertTrue(settings.service_root.is_absolute())
        self.assertEqual(Path(directory).resolve(), settings.service_root)
        with self.assertRaises(FrozenInstanceError):
            settings.port = 9000  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
