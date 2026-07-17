import re
import unittest
from pathlib import Path

from trusted_ceo_agent.cli import build_parser


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "plugin" / "trusted-ceo-agent" / "skills" / "trusted-ceo-agent" / "SKILL.md"


class SkillParityTests(unittest.TestCase):
    def test_skill_names_every_runtime_command_and_no_install_command(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        parser = build_parser()
        subparsers = next(action for action in parser._actions if action.dest == "command")
        for command in subparsers.choices:
            with self.subTest(command=command):
                self.assertRegex(text, rf"(?<![\w-]){re.escape(command)}(?![\w-])")
        self.assertNotIn("uv sync", text)

    def test_skill_forbids_direct_trusted_artifact_creation(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        for phrase in ("Fact를 직접", "Signal을 직접", "등급을 직접", "승인을 자동"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
