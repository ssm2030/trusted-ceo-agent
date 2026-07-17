import tempfile
import unittest
import zipfile
from pathlib import Path

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.adapters.xlsx_preflight import XlsxLimits, preflight_xlsx


class XlsxPreflightTests(unittest.TestCase):
    def test_zip_traversal_and_macro_are_rejected(self) -> None:
        for member in ("../escape.xml", "xl/vbaProject.bin", "xl/externalLinks/externalLink1.xml"):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "bad.xlsx"
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(member, b"x")
                with self.assertRaises(ContractError):
                    preflight_xlsx(path)

    def test_compression_ratio_limit_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bomb.xlsx"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("xl/worksheets/sheet1.xml", b"0" * 10000)
            with self.assertRaises(ContractError):
                preflight_xlsx(path, XlsxLimits(max_compression_ratio=2))


if __name__ == "__main__":
    unittest.main()
