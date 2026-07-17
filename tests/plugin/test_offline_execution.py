import contextlib
import io
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trusted_ceo_agent import cli


ROOT = Path(__file__).resolve().parents[2]


class OfflineExecutionTests(unittest.TestCase):
    def test_start_makes_no_network_connection(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            mission = root / "mission.json"
            source = root / "data.json"
            mission.write_text('{"confirmed":true}', "utf-8")
            source.write_text('{}', "utf-8")
            with patch.object(socket.socket, "connect", side_effect=AssertionError("network attempted")):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = cli.main([
                        "start", "--artifact-root", str(root / "artifacts"),
                        "--mission-contract", str(mission), "--input", str(source),
                    ])
            self.assertEqual(0, code)


if __name__ == "__main__":
    unittest.main()
