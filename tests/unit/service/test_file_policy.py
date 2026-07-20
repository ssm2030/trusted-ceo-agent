from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from openpyxl import Workbook
from trusted_ceo_agent.application import (
    AttachSourcesRequest,
    CreateRunRequest,
    SourceUpload,
    TrustedCeoApplication,
)
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.service.file_policy import (
    IncomingUpload,
    UploadLimits,
    UploadPolicy,
)
from tests.support import confirmed_mission


ROOT = Path(__file__).resolve().parents[3]


def _stage(
    policy: UploadPolicy,
    uploads,
    *,
    existing_file_count: int = 0,
    existing_total_bytes: int = 0,
):
    return policy.stage_batch(
        uploads,
        existing_file_count=existing_file_count,
        existing_total_bytes=existing_total_bytes,
    )


def _xlsx_bytes(*, member: str = "xl/worksheets/sheet1.xml") -> bytes:
    output = io.BytesIO()
    workbook = Workbook()
    workbook.active["A1"] = "trusted"
    workbook.save(output)
    workbook.close()
    if member != "xl/worksheets/sheet1.xml":
        with zipfile.ZipFile(output, "a") as archive:
            archive.writestr(member, b"<malicious />")
    return output.getvalue()


def _xlsx_with_external_relationship() -> bytes:
    source = io.BytesIO(_xlsx_bytes())
    output = io.BytesIO()
    relationship_path = "xl/_rels/workbook.xml.rels"
    with zipfile.ZipFile(source) as existing, zipfile.ZipFile(output, "w") as archive:
        for entry in existing.infolist():
            if entry.filename != relationship_path:
                archive.writestr(entry, existing.read(entry.filename))
        archive.writestr(
            relationship_path,
            b'<Relationships><Relationship TargetMode="External" '
            b'Target="https://example.test/data.xlsx" /></Relationships>',
        )
    return output.getvalue()


def _xlsx_with_malformed_workbook_xml() -> bytes:
    source = io.BytesIO(_xlsx_bytes())
    output = io.BytesIO()
    workbook_path = "xl/workbook.xml"
    with zipfile.ZipFile(source) as existing, zipfile.ZipFile(output, "w") as archive:
        for entry in existing.infolist():
            payload = b"<workbook" if entry.filename == workbook_path else existing.read(entry.filename)
            archive.writestr(entry, payload)
    return output.getvalue()


class UploadPolicyTests(unittest.TestCase):
    def test_markdown_utf8_and_safe_logical_paths_are_staged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = UploadPolicy(Path(directory))
            item = _stage(policy, (
                IncomingUpload.from_bytes(
                    'plan.md',
                    'text/markdown; charset=utf-8',
                    b'\xef\xbb\xbf# Plan\r\n\r\nRevenue assumptions\r\n',
                    logical_path='\uc804\ub7b5\uc790\ub8cc/2026/plan.md',
                ),
            ))[0]

            self.assertEqual('\uc804\ub7b5\uc790\ub8cc/2026/plan.md', item.logical_path)
            self.assertEqual('# Plan\n\nRevenue assumptions\n', item.normalized_text)
            self.assertEqual(item.logical_path, item.public_metadata()['logical_path'])
            policy.discard(item)

    def test_markdown_binary_controls_and_unsafe_logical_paths_are_rejected(self) -> None:
        invalid = (
            (b'\xff\xfe', 'notes/bad.md'),
            (b'hello\x00world', 'notes/bad.md'),
            (b' \r\n\t', 'notes/bad.md'),
            (b'hello', '../bad.md'),
            (b'hello', 'C:/bad.md'),
            (b'hello', 'https://example.test/bad.md'),
            (b'hello', 'notes/not-the-name.md'),
            (b'hello', 'notes\\bad.md'),
        )
        with tempfile.TemporaryDirectory() as directory:
            policy = UploadPolicy(Path(directory))
            for payload, logical_path in invalid:
                with self.subTest(logical_path=logical_path, payload=payload):
                    with self.assertRaises(ContractError):
                        _stage(policy, (
                            IncomingUpload.from_bytes(
                                'bad.md',
                                'application/octet-stream',
                                payload,
                                logical_path=logical_path,
                            ),
                        ))

    def test_logical_path_is_normalized_to_nfc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = UploadPolicy(Path(directory))
            item = _stage(policy, (
                IncomingUpload.from_bytes(
                    'plan.md',
                    'text/plain',
                    b'# Plan\n',
                    logical_path='re\u0301sume\u0301/plan.md',
                ),
            ))[0]

            self.assertEqual('r\u00e9sum\u00e9/plan.md', item.logical_path)
            policy.discard(item)

    def test_allowed_streams_are_staged_without_public_path_leak(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = UploadPolicy(Path(directory))
            staged = _stage(policy, (
                IncomingUpload.from_bytes("facts.csv", "text/csv", b"name,value\na,1\n"),
                IncomingUpload.from_bytes("facts.json", "application/json", b'{"a":1}'),
                IncomingUpload.from_bytes(
                    "facts.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    _xlsx_bytes(),
                ),
            ))

            self.assertEqual(3, len(staged))
            for item in staged:
                self.assertTrue(item.private_path.is_file())
                self.assertEqual(item.filename, item.private_path.name)
                self.assertNotIn(str(item.private_path), str(item.public_metadata()))
                self.assertNotIn("private_path", item.public_metadata())
                policy.validate_staged(item)
                policy.discard(item)
                self.assertFalse(item.private_path.exists())

    def test_extension_content_type_magic_and_size_limits_are_combined(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = UploadPolicy(
                Path(directory),
                limits=UploadLimits(max_file_bytes=12, max_files=2, max_total_bytes=16),
            )
            invalid = (
                IncomingUpload.from_bytes("empty.csv", "text/csv", b""),
                IncomingUpload.from_bytes("macro.xlsm", "application/octet-stream", b"PK\x03\x04"),
                IncomingUpload.from_bytes("hidden.csv", "application/json", b"{}"),
                IncomingUpload.from_bytes("data.json.csv", "text/csv", b"a,b\n1,2\n"),
                IncomingUpload.from_bytes("payload.json", "application/json", b"<html>"),
                IncomingUpload.from_bytes("large.csv", "text/csv", b"a" * 13),
            )
            for upload in invalid:
                with self.subTest(filename=upload.filename):
                    with self.assertRaises(ContractError):
                        _stage(policy, (upload,))
            with self.assertRaises(ContractError):
                _stage(policy, (
                    IncomingUpload.from_bytes("a.csv", "text/csv", b"a,b\n"),
                    IncomingUpload.from_bytes("b.csv", "text/csv", b"a,b\n"),
                    IncomingUpload.from_bytes("c.csv", "text/csv", b"a,b\n"),
                ))
            self.assertEqual([], list((Path(directory) / "staging").iterdir()))

    def test_normal_dotted_name_is_allowed_but_executable_double_extension_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = UploadPolicy(Path(directory))
            accepted = _stage(policy, (
                IncomingUpload.from_bytes("q2.final.csv", "text/csv", b"a,b\n1,2\n"),
            ))[0]
            self.assertEqual("q2.final.csv", accepted.private_path.name)
            policy.discard(accepted)
            with self.assertRaises(ContractError):
                _stage(policy, (IncomingUpload.from_bytes(
                    "evil.exe.csv", "text/csv", b"a,b\n1,2\n",
                ),))

    def test_existing_run_usage_is_included_in_count_and_byte_limits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = UploadPolicy(
                Path(directory),
                limits=UploadLimits(max_file_bytes=8, max_files=2, max_total_bytes=12),
            )
            with self.assertRaises(ContractError):
                _stage(policy,
                    (IncomingUpload.from_bytes("b.csv", "text/csv", b"a,b\n"),),
                    existing_file_count=2,
                    existing_total_bytes=8,
                )
            with self.assertRaises(ContractError):
                _stage(policy,
                    (IncomingUpload.from_bytes("b.csv", "text/csv", b"a,b\n1,2\n"),),
                    existing_file_count=1,
                    existing_total_bytes=8,
                )

    def test_staged_original_name_and_media_type_survive_engine_attachment(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            service_root = Path(directory) / "runtime"
            application = TrustedCeoApplication(service_root / "runs")
            run_id = "run_upload_identity_12345678"
            created = application.create_run(CreateRunRequest(
                mission=confirmed_mission(),
                run_id=run_id,
            ))
            policy = UploadPolicy(service_root)
            item = _stage(policy, (IncomingUpload.from_bytes(
                "q2.final.csv",
                "text/csv",
                b"name,value\na,1\n",
            ),))[0]

            attached = application.attach_sources(AttachSourcesRequest(
                run_id=run_id,
                expected_revision=created.revision or 0,
                sources=(SourceUpload(
                    path=item.private_path,
                    opaque_token=item.opaque_token,
                    expected_sha256=item.sha256,
                    expected_size=item.size,
                ),),
            ))

            registry_path = (
                service_root / "runs" / run_id / "snapshots"
                / f"r{attached.revision:04d}" / "sources" / "registry.json"
            )
            registry = json.loads(registry_path.read_text("utf-8"))
            self.assertEqual("q2.final.csv", registry[0]["display_name"])
            self.assertEqual("text/csv", registry[0]["media_type"])
            policy.discard(item)

    def test_engine_attachment_rejects_staged_file_changed_after_policy_validation(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            service_root = Path(directory) / "runtime"
            application = TrustedCeoApplication(service_root / "runs")
            run_id = "run_upload_tamper_12345678"
            created = application.create_run(CreateRunRequest(
                mission=confirmed_mission(),
                run_id=run_id,
            ))
            policy = UploadPolicy(service_root)
            item = _stage(policy, (IncomingUpload.from_bytes(
                "facts.csv", "text/csv", b"name,value\na,1\n",
            ),))[0]
            item.private_path.write_bytes(b"name,value\na,999\n")

            with self.assertRaises(ContractError):
                application.attach_sources(AttachSourcesRequest(
                    run_id=run_id,
                    expected_revision=created.revision or 0,
                    sources=(SourceUpload(
                        path=item.private_path,
                        opaque_token=item.opaque_token,
                        expected_sha256=item.sha256,
                        expected_size=item.size,
                    ),),
                ))

            state = json.loads(
                (service_root / "runs" / run_id / "state.json").read_text("utf-8")
            )
            self.assertEqual(created.revision, state["revision"])
            item.private_path.unlink()
            item.private_path.parent.rmdir()

    def test_xlsx_active_external_and_traversal_members_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = UploadPolicy(Path(directory))
            for member in (
                "../escape.xml",
                "xl/vbaProject.bin",
                "xl/externalLinks/externalLink1.xml",
            ):
                with self.subTest(member=member):
                    with self.assertRaises(ContractError):
                        _stage(policy, (IncomingUpload.from_bytes(
                            "facts.xlsx",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            _xlsx_bytes(member=member),
                        ),))
            with self.assertRaises(ContractError):
                _stage(policy, (IncomingUpload.from_bytes(
                    "facts.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    _xlsx_with_external_relationship(),
                ),))
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("random.txt", b"not a workbook")
            with self.assertRaises(ContractError):
                _stage(policy, (IncomingUpload.from_bytes(
                    "facts.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    output.getvalue(),
                ),))

    def test_malformed_xlsx_xml_is_a_contract_error_and_staging_is_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = UploadPolicy(root)

            with self.assertRaisesRegex(ContractError, "structure is invalid"):
                _stage(policy, (IncomingUpload.from_bytes(
                    "facts.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    _xlsx_with_malformed_workbook_xml(),
                ),))

            self.assertEqual([], list((root / "staging").iterdir()))

    def test_replaced_symlink_or_hardlink_staging_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = UploadPolicy(Path(directory))
            item = _stage(policy, (
                IncomingUpload.from_bytes("facts.csv", "text/csv", b"a,b\n1,2\n"),
            ))[0]
            hardlink = item.private_path.with_suffix(".hardlink")
            try:
                hardlink.hardlink_to(item.private_path)
                with self.assertRaises(ValueError):
                    policy.validate_staged(item)
            finally:
                hardlink.unlink(missing_ok=True)
                policy.discard(item)


if __name__ == "__main__":
    unittest.main()
