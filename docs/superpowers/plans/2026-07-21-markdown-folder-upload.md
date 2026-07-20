# Markdown Evidence and Cumulative Folder Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cumulative file/folder uploads with safe logical relative paths and make uploaded Markdown a validated, line-addressable AI evidence type.

**Architecture:** The browser normalizes file and directory selections into `AnalysisUpload` values, while the Python service remains the authority for cumulative sources and returns a sanitized `uploaded_files` snapshot. Markdown is decoded and chunked deterministically into first-class Document Evidence, carried only in bounded lens jobs, and accepted by claim/evidence validators only when its ID, hash, source, and allowlist all match.

**Tech Stack:** Next.js 16, React 19, TypeScript 5.9, Vitest, Testing Library, FastAPI, Python 3.11, Pydantic, JSON Schema Draft 2020-12, `unittest`, `uv`, Playwright.

---

## Execution constraints

- Work only in `C:\Users\home\Desktop\개인 작업\해커톤\trusted-ceo-agent`.
- Do not create or use a path below `C:\Users\home\.codex\worktrees`.
- Do not read, print, stage, or commit `.env.local` or `OPENAI_API_KEY`.
- Preserve user changes in `.gitignore`, `AGENTS.md`, and `web/next-env.d.ts`.
- Preserve unrelated untracked evaluation, documentation, fixture, and recovery files.
- Use `apply_patch` for edits.
- Start every behavior change with a focused RED test and verify the expected failure before production code.
- Run only one heavyweight suite or build at a time.
- Commit only the files named by the current task.

## File map

### New focused modules

- `web/src/features/analysis/upload-selection.ts`: browser file/folder normalization, extension filtering, logical-path validation, and collection labels.
- `web/src/features/analysis/__tests__/upload-selection.test.ts`: pure browser selection policy tests.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/document_evidence.py`: UTF-8 Markdown normalization, heading-aware chunking, stable IDs, hashes, and registry validation helpers.
- `plugin/trusted-ceo-agent/schemas/document-evidence.schema.json`: strict Document Evidence item contract.
- `tests/unit/intake/test_document_evidence.py`: deterministic Markdown chunking and tamper tests.

### Existing web files to modify

- `web/src/features/analysis/analysis-model.ts`: shared `AnalysisUpload` and `UploadedFileSummary` types.
- `web/src/features/analysis/analysis-provider.ts`: add `uploaded_files` and change `attachData` to accept normalized uploads.
- `web/src/features/analysis/DataUploadCard.tsx`: separate file/folder controls, skipped-file notice, grouped canonical list.
- `web/src/features/analysis/LiveAnalysisCommandCenter.tsx`: render server-canonical uploads and respect `attach_data` availability.
- `web/src/features/analysis/ReplayCommandCenter.tsx`: accumulate replay metadata with the same UI contract.
- `web/src/features/analysis/replay-provider.ts`: accept Markdown and accumulate normalized uploads.
- `web/src/features/analysis/remote-provider.ts`: send repeated `files` and aligned `logical_paths`.
- `web/src/lib/server/analysis/types.ts`: validate backend `uploaded_files` summaries.
- `web/src/lib/server/analysis/route-handlers.ts`: validate and forward aligned logical paths.
- `web/src/app/globals.css`: folder controls, skipped-file notice, and grouped-list styling.
- Related tests under `web/src/features/analysis/__tests__/` and `web/src/lib/server/analysis/__tests__/`.

### Existing Python files to modify

- `plugin/trusted-ceo-agent/trusted_ceo_agent/service/file_policy.py`: `.md`, logical paths, UTF-8/control-character validation.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/service/app.py`: receive repeated `logical_paths`.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/service/contracts.py`: sanitized uploaded-file snapshot type.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/service/orchestrator.py`: cumulative logical-path limits, SourceUpload propagation, canonical upload summaries, `attach_data` action.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/application/models.py`: add `logical_path` to `SourceUpload`.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/application/run_application.py`: immutable logical-path/source merge rules and Markdown media type.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/runtime_scan.py`: create Document Evidence instead of an unsupported-type issue.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/evidence/core.py`: assemble and validate the document register and document Evidence Links.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/reasoning/jobs.py`: bounded Document Evidence context and combined sharding.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/reasoning/ref_validation.py`: document allowlist checks.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/reasoning/normalizer.py`: track used document IDs and materialize document links.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutations.py`: put registered chunks into lens jobs.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/service/openai_gateway.py`: revalidate the bounded untrusted context immediately before transport.
- `plugin/trusted-ceo-agent/schemas/evidence-core.schema.json`, `evidence-link.schema.json`, `reasoning-job.schema.json`, `lens-card-draft.schema.json`, and `normalized-card.schema.json`: optional backward-compatible document fields.
- Focused tests under `tests/unit/service/`, `tests/unit/application/`, `tests/unit/evidence/`, and `tests/unit/reasoning/`.

## Task 1: Python upload policy accepts safe Markdown and logical paths

**Files:**
- Modify: `tests/unit/service/test_file_policy.py`
- Modify: `tests/unit/service/test_app.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/service/file_policy.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/service/app.py`

- [ ] **Step 1: Write focused RED tests for Markdown and relative-path validation**

Add tests equivalent to the following to `UploadPolicyTests`:

```python
def test_markdown_utf8_and_safe_logical_paths_are_staged(self) -> None:
    with tempfile.TemporaryDirectory() as directory:
        policy = UploadPolicy(Path(directory))
        item = _stage(policy, (IncomingUpload.from_bytes(
            "plan.md",
            "text/markdown",
            "# 계획\r\n\r\n매출 원인을 검토한다.\r\n".encode("utf-8"),
            logical_path="전략자료/2026/plan.md",
        ),))[0]
        self.assertEqual("전략자료/2026/plan.md", item.logical_path)
        self.assertEqual("# 계획\n\n매출 원인을 검토한다.\n", item.normalized_text)
        policy.discard(item)

def test_markdown_binary_controls_and_unsafe_logical_paths_are_rejected(self) -> None:
    invalid = (
        (b"\xff\xfe", "자료/bad.md"),
        (b"hello\x00world", "자료/nul.md"),
        (b"hello", "../escape.md"),
        (b"hello", "C:/secret.md"),
        (b"hello", "https://example.test/x.md"),
        (b"hello", "자료/not-the-name.md"),
    )
    with tempfile.TemporaryDirectory() as directory:
        for payload, logical_path in invalid:
            with self.subTest(logical_path=logical_path):
                policy = UploadPolicy(Path(directory))
                with self.assertRaises(ContractError):
                    _stage(policy, (IncomingUpload.from_bytes(
                        "bad.md", "application/octet-stream", payload,
                        logical_path=logical_path,
                    ),))
```

Add a FastAPI route test to `tests/unit/service/test_app.py` that posts two `files` and two `logical_paths`, then asserts the orchestrator receives them in the same order. Add a second test with one missing path and assert HTTP 422 with `INPUT_POLICY_FAILURE`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.service.test_file_policy tests.unit.service.test_app -q
```

Expected: FAIL because `IncomingUpload.from_bytes` has no `logical_path`, `StagedUpload` has no normalized Markdown fields, `.md` is rejected, and the route ignores `logical_paths`.

- [ ] **Step 3: Implement the minimal upload-policy contract**

Extend the data types without changing defaults for existing callers:

```python
@dataclass(frozen=True, slots=True)
class IncomingUpload:
    filename: str
    content_type: str
    chunks: Iterable[bytes]
    logical_path: str | None = None

    @classmethod
    def from_bytes(
        cls,
        filename: str,
        content_type: str,
        payload: bytes,
        *,
        logical_path: str | None = None,
    ) -> IncomingUpload:
        return cls(filename, content_type, (payload,), logical_path)

@dataclass(frozen=True, slots=True)
class StagedUpload:
    opaque_token: str
    filename: str
    logical_path: str
    content_type: str
    size: int
    sha256: str
    private_path: Path
    normalized_text: str | None = None
```

Add `.md` content types and a strict path validator:

```python
_CONTENT_TYPES[".md"] = frozenset({
    "text/markdown",
    "text/x-markdown",
    "text/plain",
    "application/octet-stream",
})

def _validated_logical_path(filename: str, value: str | None) -> str:
    logical = unicodedata.normalize("NFC", value or filename)
    if not logical or len(logical) > 512 or "\\" in logical or logical.startswith("/"):
        raise ContractError("upload logical path is invalid")
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", logical):
        raise ContractError("upload logical path must be relative")
    parts = logical.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ContractError("upload logical path contains an unsafe segment")
    if any(any(unicodedata.category(character) == "Cc" for character in part) for part in parts):
        raise ContractError("upload logical path contains control characters")
    if parts[-1] != unicodedata.normalize("NFC", filename):
        raise ContractError("upload logical path basename does not match filename")
    return logical

def _normalized_markdown(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ContractError("Markdown upload must be UTF-8") from error
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        raise ContractError("empty Markdown upload is forbidden")
    if any(character != "\n" and character != "\t" and unicodedata.category(character) == "Cc" for character in normalized):
        raise ContractError("Markdown upload contains forbidden control characters")
    return normalized
```

Call `_validated_logical_path` before staging. For `.md`, read the private file once after streaming, call `_normalized_markdown`, and store its result on `StagedUpload`; keep CSV/JSON/XLSX validation unchanged.

Change the FastAPI route signature to `logical_paths: list[str] | None = Form(default=None)`. If absent, use filenames. If present, require exactly one path per file and pass each path into its `IncomingUpload`.

- [ ] **Step 4: Run focused GREEN tests**

Run the Step 2 command again.

Expected: PASS; existing CSV/JSON/XLSX tests remain green, Markdown policy failures are contract failures, and multipart order is preserved.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- tests/unit/service/test_file_policy.py tests/unit/service/test_app.py plugin/trusted-ceo-agent/trusted_ceo_agent/service/file_policy.py plugin/trusted-ceo-agent/trusted_ceo_agent/service/app.py
git commit -m "feat: validate markdown uploads and logical paths"
```

## Task 2: Application Source Registry accumulates immutable logical paths

**Files:**
- Modify: `tests/unit/application/test_run_application.py`
- Modify: `tests/unit/service/test_orchestrator_context.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/models.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/run_application.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/service/contracts.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/service/orchestrator.py`

- [ ] **Step 1: Write RED tests for aliasing, collisions, count limits, and snapshots**

Add application tests with these assertions:

```python
first = SourceUpload(
    path=workspace / "a.md",
    opaque_token="upload-a",
    logical_path="폴더A/a.md",
)
alias = SourceUpload(
    path=workspace / "copy.md",
    opaque_token="upload-copy",
    logical_path="폴더B/copy.md",
)
conflict = SourceUpload(
    path=workspace / "changed.md",
    opaque_token="upload-changed",
    logical_path="폴더A/a.md",
)
```

Attach `first`, attach the byte-identical `alias`, and assert one Source with
`display_name == "폴더A/a.md"` and `aliases == ["폴더B/copy.md"]`. Then attach
`conflict` with different bytes and assert `ContractError`, unchanged revision, and unchanged registry bytes.

Add orchestrator tests that create a run, upload two batches, and assert:

```python
self.assertEqual(
    ["폴더A/a.md", "폴더B/b.csv"],
    [item.logical_path for item in second.uploaded_files],
)
self.assertIn("attach_data", second.allowed_actions)
self.assertNotIn("private_path", second.model_dump_json())
self.assertNotIn("snapshot_ref", second.model_dump_json())
```

Add a limit test where aliases make the 65th unique logical path fail even when all payload hashes are identical.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.application.test_run_application tests.unit.service.test_orchestrator_context -q
```

Expected: FAIL because `SourceUpload` has no logical path, path conflicts are not detected, file limits use Source count, snapshots have no `uploaded_files`, and `attach_data` is absent.

- [ ] **Step 3: Implement immutable path accumulation and sanitized summaries**

Extend `SourceUpload` compatibly:

```python
@dataclass(frozen=True, slots=True)
class SourceUpload:
    path: Path
    opaque_token: str
    expected_sha256: str | None = None
    expected_size: int | None = None
    logical_path: str | None = None
```

Change `_source_document` to accept `display_name: str | None = None`, use the
logical path for `display_name`, derive media type from `Path(display_name).suffix`, and derive the opaque path token from `{name: display_name, sha256: digest}`. Before merging a batch, build a map from every existing `display_name` and `alias` to its Source ID. Apply these exact rules:

Add `.md: text/markdown` to `_MEDIA_TYPES` so the Source Registry does not
fall back to `application/octet-stream` after Markdown validation.

```python
if existing_path_source is not None and existing_path_source != document["source_id"]:
    raise ContractError("upload logical path already exists with different content")
if document["source_id"] in sources_by_id:
    _merge_source(sources_by_id, document)
else:
    sources_by_id[document["source_id"]] = document
```

Count `display_name` plus aliases for `existing_file_count`. Keep stored byte
usage based on unique Source blobs. Include `logical_path` in the idempotency
receipt and pass `StagedUpload.logical_path` to `SourceUpload`.

Add strict public snapshot models:

```python
class UploadedFileSummary(StrictModel):
    source_id: str = Field(pattern=r"^source_[0-9a-f]{24}$")
    logical_path: str = Field(min_length=1, max_length=512)
    display_name: str = Field(min_length=1, max_length=512)
    media_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(ge=0)
    collection_label: str = Field(min_length=1, max_length=512)

class RunSnapshot(StrictModel):
    uploaded_files: list[UploadedFileSummary] = Field(default_factory=list, max_length=64)
```

Build summaries from Source `display_name` plus aliases, sort them by logical
path, use the first segment as `collection_label` when the path contains `/`,
use `개별 파일` otherwise, and set public `display_name` to the final path
segment while preserving the full value in `logical_path`. Never include SHA, resolver tokens, blob refs,
or filesystem paths. Add `attach_data` only while source attachment is allowed
and no model/HITL artifact has started.

- [ ] **Step 4: Run focused GREEN tests**

Run the Step 2 command again.

Expected: PASS; multiple batches accumulate, aliases remain immutable, the 64-path limit is enforced, and snapshots reveal only public summaries.

- [ ] **Step 5: Commit Task 2**

```powershell
git add -- tests/unit/application/test_run_application.py tests/unit/service/test_orchestrator_context.py plugin/trusted-ceo-agent/trusted_ceo_agent/application/models.py plugin/trusted-ceo-agent/trusted_ceo_agent/application/run_application.py plugin/trusted-ceo-agent/trusted_ceo_agent/service/contracts.py plugin/trusted-ceo-agent/trusted_ceo_agent/service/orchestrator.py
git commit -m "feat: accumulate canonical uploaded source paths"
```

## Task 3: Web transport carries aligned logical paths and canonical summaries

**Files:**
- Modify: `web/src/features/analysis/analysis-model.ts`
- Modify: `web/src/features/analysis/analysis-provider.ts`
- Modify: `web/src/features/analysis/remote-provider.ts`
- Modify: `web/src/features/analysis/replay-provider.ts`
- Modify: `web/src/lib/server/analysis/types.ts`
- Modify: `web/src/lib/server/analysis/route-handlers.ts`
- Modify: `web/src/features/analysis/__tests__/remote-provider.test.ts`
- Modify: `web/src/features/analysis/__tests__/replay-provider.test.ts`
- Modify: `web/src/lib/server/analysis/__tests__/route-handlers.test.ts`

- [ ] **Step 1: Write transport RED tests**

In `remote-provider.test.ts`, call `attachData` with:

```ts
const uploads = [
  {
    file: new File(["# A"], "a.md", { type: "text/markdown" }),
    logicalPath: "폴더A/a.md",
    collectionLabel: "폴더A",
  },
  {
    file: new File(["x,y\n1,2\n"], "b.csv", { type: "text/csv" }),
    logicalPath: "폴더B/b.csv",
    collectionLabel: "폴더B",
  },
];
```

Inspect the posted `FormData` and assert `files` and `logical_paths` have length
2 and matching order. Make the fake response include two `uploaded_files` and
assert they survive `parseSnapshot`.

In `route-handlers.test.ts`, import `handleAnalysisFiles`, send a multipart
request with two files/two paths, and assert the backend FormData preserves the
pairing. Add a mismatch test expecting 422 and no backend call.

In `replay-provider.test.ts`, attach two batches and assert the second snapshot
contains both uploaded paths and accepts `.md`.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
npm --prefix web run test:focused -- src/features/analysis/__tests__/remote-provider.test.ts src/features/analysis/__tests__/replay-provider.test.ts src/lib/server/analysis/__tests__/route-handlers.test.ts
```

Expected: FAIL because `AnalysisUpload`, `uploaded_files`, `logical_paths`, and cumulative replay snapshots do not exist.

- [ ] **Step 3: Implement the web/provider contracts**

Add these types to `analysis-model.ts`:

```ts
export type AnalysisUpload = Readonly<{
  file: File;
  logicalPath: string;
  collectionLabel: string;
}>;

export type UploadedFileSummary = Readonly<{
  source_id: string;
  logical_path: string;
  display_name: string;
  media_type: string;
  size_bytes: number;
  collection_label: string;
}>;
```

Make `ProviderSnapshot.uploaded_files` required and change
`AnalysisProvider.attachData(runId: string, expectedRevision: number, uploads: AnalysisUpload[])`. Update every
snapshot fixture with `uploaded_files: []`.

In `RemoteAnalysisProvider.attachData`, append paired values:

```ts
for (const upload of uploads) {
  form.append("files", upload.file, upload.file.name);
  form.append("logical_paths", upload.logicalPath);
}
```

Validate each backend summary with exact types, integer nonnegative sizes,
safe relative paths, a 64-item maximum, and unique logical paths. In the BFF,
default all paths to `file.name` only when no `logical_paths` are present;
otherwise require equal counts. Validate the same path policy as Task 1 and
forward paired entries.

In replay mode, use `logical_path` as the unique key. Re-attaching the same
path/size/type is idempotent; a changed value at the same path returns a
`CONTRACT_FAILURE`; successful distinct paths append to `uploaded_files`.

- [ ] **Step 4: Run focused GREEN tests and one typecheck**

Run sequentially:

```powershell
npm --prefix web run test:focused -- src/features/analysis/__tests__/remote-provider.test.ts src/features/analysis/__tests__/replay-provider.test.ts src/lib/server/analysis/__tests__/route-handlers.test.ts
npm --prefix web run typecheck
```

Expected: all focused tests PASS and typecheck exits 0.

- [ ] **Step 5: Commit Task 3**

```powershell
git add -- web/src/features/analysis/analysis-model.ts web/src/features/analysis/analysis-provider.ts web/src/features/analysis/remote-provider.ts web/src/features/analysis/replay-provider.ts web/src/lib/server/analysis/types.ts web/src/lib/server/analysis/route-handlers.ts web/src/features/analysis/__tests__/remote-provider.test.ts web/src/features/analysis/__tests__/replay-provider.test.ts web/src/lib/server/analysis/__tests__/route-handlers.test.ts
git commit -m "feat: carry logical upload paths through web transport"
```

## Task 4: File and folder UI accumulates canonical grouped sources

**Files:**
- Create: `web/src/features/analysis/upload-selection.ts`
- Create: `web/src/features/analysis/__tests__/upload-selection.test.ts`
- Modify: `web/src/features/analysis/DataUploadCard.tsx`
- Modify: `web/src/features/analysis/LiveAnalysisCommandCenter.tsx`
- Modify: `web/src/features/analysis/ReplayCommandCenter.tsx`
- Modify: `web/src/features/analysis/__tests__/LiveAnalysisCommandCenter.test.tsx`
- Modify: `web/src/features/analysis/__tests__/ReplayCommandCenter.test.tsx`
- Modify: `web/src/app/globals.css`

- [ ] **Step 1: Write pure selection and component RED tests**

Create `upload-selection.test.ts` with these cases:

```ts
it("keeps supported files recursively and reports skipped folder files", () => {
  const md = new File(["# 전략"], "plan.md", { type: "text/markdown" });
  Object.defineProperty(md, "webkitRelativePath", { value: "전략/2026/plan.md" });
  const exe = new File(["x"], "run.exe", { type: "application/octet-stream" });
  Object.defineProperty(exe, "webkitRelativePath", { value: "전략/bin/run.exe" });
  expect(normalizeUploadSelection([md, exe], "folder")).toEqual({
    uploads: [{ file: md, logicalPath: "전략/2026/plan.md", collectionLabel: "전략" }],
    skippedCount: 1,
  });
});

it("rejects unsafe browser relative paths", () => {
  const file = new File(["# bad"], "bad.md", { type: "text/markdown" });
  Object.defineProperty(file, "webkitRelativePath", { value: "../bad.md" });
  expect(() => normalizeUploadSelection([file], "folder")).toThrow(
    "안전하지 않은 폴더 경로",
  );
});
```

Extend `LiveAnalysisCommandCenter.test.tsx` so the provider returns canonical
`uploaded_files` from two batches, then assert both folder groups remain and
the input disables when `attach_data` disappears. Extend replay tests to select
two folder batches and assert both groups persist.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
npm --prefix web run test:focused -- src/features/analysis/__tests__/upload-selection.test.ts src/features/analysis/__tests__/LiveAnalysisCommandCenter.test.tsx src/features/analysis/__tests__/ReplayCommandCenter.test.tsx
```

Expected: FAIL because the selection module and folder input do not exist and both command centers replace local lists.

- [ ] **Step 3: Implement selection normalization and grouped UI**

Create `upload-selection.ts` with a case-insensitive extension set and this
public function:

```ts
const ALLOWED_EXTENSIONS = new Set(["csv", "json", "xlsx", "md"]);
const URI_OR_DRIVE = /^[A-Za-z][A-Za-z0-9+.-]*:/u;

export function normalizeUploadSelection(
  files: Iterable<File>,
  mode: "files" | "folder",
): { uploads: AnalysisUpload[]; skippedCount: number } {
  const uploads: AnalysisUpload[] = [];
  let skippedCount = 0;
  for (const file of files) {
    const extension = file.name.split(".").pop()?.toLocaleLowerCase("en-US") ?? "";
    if (!ALLOWED_EXTENSIONS.has(extension)) {
      if (mode === "folder") { skippedCount += 1; continue; }
      throw new Error("분석 자료는 CSV, JSON, XLSX, MD 파일만 선택할 수 있습니다.");
    }
    const raw = mode === "folder" ? file.webkitRelativePath : file.name;
    const logicalPath = raw.normalize("NFC");
    const parts = logicalPath.split("/");
    const unsafe = !logicalPath || logicalPath.length > 512 || logicalPath.startsWith("/") ||
      logicalPath.includes("\\") || URI_OR_DRIVE.test(logicalPath) ||
      parts.some((part) => !part || part === "." || part === ".." || /[\u0000-\u001F\u007F]/u.test(part)) ||
      parts.at(-1) !== file.name.normalize("NFC");
    if (unsafe) throw new Error("안전하지 않은 폴더 경로가 포함되어 있습니다.");
    uploads.push({
      file,
      logicalPath,
      collectionLabel: mode === "folder" ? parts[0] : "개별 파일",
    });
  }
  return { uploads, skippedCount };
}
```

In `DataUploadCard`, keep the multiple file input and add a second input whose
ref sets `webkitdirectory=""` and `directory=""`. Use the common normalizer,
clear `event.currentTarget.value` after copying the `FileList`, show the skipped
count as a status note, and do not call the provider when accepted count is 0.
Group `files` by `collection_label` and render `logical_path`.

Live mode must render `snapshot.uploaded_files` directly. Replay mode must
render the replay snapshot summaries. Remove browser-local live filename state;
keep only the approved run ID in session storage. Disable both inputs when busy
or `!snapshot.allowed_actions.includes("attach_data")`.

- [ ] **Step 4: Run focused GREEN tests and typecheck**

Run sequentially:

```powershell
npm --prefix web run test:focused -- src/features/analysis/__tests__/upload-selection.test.ts src/features/analysis/__tests__/LiveAnalysisCommandCenter.test.tsx src/features/analysis/__tests__/ReplayCommandCenter.test.tsx
npm --prefix web run typecheck
```

Expected: tests PASS, typecheck exits 0, and no filename metadata is added to live sessionStorage.

- [ ] **Step 5: Commit Task 4**

```powershell
git add -- web/src/features/analysis/upload-selection.ts web/src/features/analysis/__tests__/upload-selection.test.ts web/src/features/analysis/DataUploadCard.tsx web/src/features/analysis/LiveAnalysisCommandCenter.tsx web/src/features/analysis/ReplayCommandCenter.tsx web/src/features/analysis/__tests__/LiveAnalysisCommandCenter.test.tsx web/src/features/analysis/__tests__/ReplayCommandCenter.test.tsx web/src/app/globals.css
git commit -m "feat: add cumulative folder upload interface"
```

## Task 5: Deterministic Markdown Document Evidence

**Files:**
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/document_evidence.py`
- Create: `plugin/trusted-ceo-agent/schemas/document-evidence.schema.json`
- Create: `tests/unit/intake/test_document_evidence.py`

- [ ] **Step 1: Write RED tests for deterministic chunks and tamper detection**

Create tests that build a source dict with a real Source ID and call
`build_document_evidence`. Cover headings outside fences, heading-looking text
inside fences, CRLF/LF equivalence, a 2,001-character line, stable byte-for-byte
output, and mutation of `content_sha256`, `line_start`, and `source_id`.

The primary expectation must include concrete locators:

```python
self.assertEqual(
    [("개요", 1, 3), ("세부/리스크", 4, 7)],
    [
        ("/".join(item["heading_path"]), item["line_start"], item["line_end"])
        for item in evidence
    ],
)
self.assertTrue(all(len(item["content"]) <= 2_000 for item in evidence))
self.assertTrue(all(item["locator_type"] == "markdown_lines" for item in evidence))
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.intake.test_document_evidence -q
```

Expected: import failure because the module and schema do not exist.

- [ ] **Step 3: Implement the strict schema and deterministic parser**

Define constants and public functions:

```python
MAX_CHUNK_CHARACTERS = 2_000

def build_document_evidence(
    source: Mapping[str, Any],
    normalized_text: str,
) -> list[dict[str, Any]]:
    document_hash = hashlib.sha256(normalized_text.encode(utf-8)).hexdigest()
    chunks = _bounded_markdown_chunks(_markdown_sections(normalized_text))
    result: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        content = str(chunk[content])
        content_hash = hashlib.sha256(content.encode(utf-8)).hexdigest()
        seed = {
            source_id: source[source_id],
            normalized_document_sha256: document_hash,
            chunk_index: index,
            line_start: chunk[line_start],
            line_end: chunk[line_end],
            content_sha256: content_hash,
        }
        body = {
            document_evidence_id: make_id(document, seed),
            source_id: source[source_id],
            logical_path: source[display_name],
            chunk_index: index,
            heading_path: chunk[heading_path],
            line_start: chunk[line_start],
            line_end: chunk[line_end],
            content: content,
            content_sha256: content_hash,
            normalized_document_sha256: document_hash,
            locator_type: markdown_lines,
        }
        item = {
            **body,
            integrity: {
                payload_hash: hashlib.sha256(canonical_bytes(body)).hexdigest(),
            },
        }
        SchemaStore().validate(document-evidence.schema.json, item)
        result.append(item)
    return result

def validate_document_evidence_registry(
    source: Mapping[str, Any],
    normalized_text: str,
    registry: Sequence[Mapping[str, Any]],
) -> None:
    expected = build_document_evidence(source, normalized_text)
    if canonical_bytes(list(expected)) != canonical_bytes(list(registry)):
        raise IntegrityError("Document Evidence registry does not match its Source")
```

Implement `_markdown_sections` and `_bounded_markdown_chunks` as private,
model-free helpers. `_markdown_sections` returns dictionaries with
`heading_path` and numbered `lines`; `_bounded_markdown_chunks` returns
`heading_path`, `line_start`, `line_end`, and `content`. Use this exact
algorithm:

1. Split normalized text with `splitlines(keepends=True)` and number lines from 1.
2. Track backtick or tilde fences using the opening marker length; ignore headings until the matching fence closes.
3. Recognize `^(#{1,6})[ \t]+(.+?)#*[ \t]*$` only outside fences.
4. Maintain a six-level heading stack and start a new section at each heading.
5. Append complete lines until adding one would exceed 2,000 characters.
6. Split a single overlong line at Unicode character boundaries while keeping its original line number.
7. Build the ID from canonical `{source_id, normalized_document_sha256, chunk_index, line_start, line_end, content_sha256}` using `make_id("document", body)`.
8. Add `integrity.payload_hash` over every field except `integrity` and validate each item with `SchemaStore`.

The JSON Schema must be `additionalProperties: false`, require every field from
the approved design, enforce `document_[0-9a-f]{24}`, positive chunk/line
integers, 64-character lowercase SHA-256 values, `content` length 1..2000, and
`locator_type: "markdown_lines"`.

- [ ] **Step 4: Run focused GREEN tests**

Run the Step 2 command again.

Expected: PASS for deterministic LF/CRLF normalization, fences, long lines, IDs, hashes, and tamper rejection.

- [ ] **Step 5: Commit Task 5**

```powershell
git add -- plugin/trusted-ceo-agent/trusted_ceo_agent/intake/document_evidence.py plugin/trusted-ceo-agent/schemas/document-evidence.schema.json tests/unit/intake/test_document_evidence.py
git commit -m "feat: add deterministic markdown evidence chunks"
```

## Task 6: Runtime scan and Evidence Core register document evidence

**Files:**
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/runtime_scan.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/evidence/core.py`
- Modify: `plugin/trusted-ceo-agent/schemas/evidence-core.schema.json`
- Modify: `plugin/trusted-ceo-agent/schemas/evidence-link.schema.json`
- Modify: `tests/unit/evidence/test_evidence_builders.py`
- Modify: `tests/unit/service/test_orchestrator_context.py`

- [ ] **Step 1: Write RED tests for scan registration and Source lineage**

Add a runtime/orchestrator test that uploads `전략/plan.md`, advances through
scan, and asserts:

```python
core = strict_loads(files["evidence/core.json"])
self.assertGreater(len(core["document_evidence_register"]), 0)
self.assertEqual([], [
    item for item in core["data_quality_register"]
    if item.get("reason_code") == "source_parse_failed"
])
self.assertEqual([], core["fact_register"])
self.assertEqual([], core["capability_map"]["capabilities"])
```

In `test_evidence_builders.py`, create one Source and one document item, validate
the core, then assert unknown Source, changed content hash, changed Source blob,
and duplicate document IDs raise `IntegrityError`.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.evidence.test_evidence_builders tests.unit.service.test_orchestrator_context -q
```

Expected: FAIL because the Evidence Core schema and runtime scan have no document register and `.md` remains an unsupported blocking type.

- [ ] **Step 3: Implement scan branching and backward-compatible core assembly**

In `runtime_scan.py`, branch before `select_adapter`:

```python
if Path(str(source["display_name"])).suffix.casefold() == ".md":
    normalized = normalize_markdown_blob(blob.read_bytes())
    chunks = build_document_evidence(source, normalized)
    document_evidence.extend(chunks)
    updates[f"intake/document-evidence/{source_id}.json"] = canonical_bytes(list(chunks))
    parsed_count += 1
    continue
```

Do not create Dataset, mapping proposals, Facts, or capability coverage from
Markdown. Add the sorted document IDs to the semantic fingerprint seed.

Extend `assemble_evidence_core` with
`document_evidence_register: Sequence[Mapping[str, Any]] = ()` and emit the
sorted register for new cores. Make the JSON Schema field optional so old stored
cores still validate; validators use `core.get("document_evidence_register", [])`.
Validate every document against its Source blob by normalizing and rebuilding
the Source-specific registry.

Extend Evidence Link schema with `evidence_kind: "document"` and
`evidence_ref: ^(fact|signal|document)_[0-9a-f]{24}$`. Keep `value_refs`
restricted to Fact and Signal.

- [ ] **Step 4: Run focused GREEN tests and schema contract tests**

Run sequentially:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.evidence.test_evidence_builders tests.unit.service.test_orchestrator_context -q
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.contracts.test_core_evidence_schemas tests.unit.test_runtime_policy -q
```

Expected: PASS; old cores without the field validate, new Markdown cores reach Source bytes, and no structured Fact is fabricated.

- [ ] **Step 5: Commit Task 6**

```powershell
git add -- plugin/trusted-ceo-agent/trusted_ceo_agent/runtime_scan.py plugin/trusted-ceo-agent/trusted_ceo_agent/evidence/core.py plugin/trusted-ceo-agent/schemas/evidence-core.schema.json plugin/trusted-ceo-agent/schemas/evidence-link.schema.json tests/unit/evidence/test_evidence_builders.py tests/unit/service/test_orchestrator_context.py
git commit -m "feat: register markdown in the evidence core"
```

## Task 7: Lens jobs carry bounded untrusted document context

**Files:**
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/reasoning/jobs.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutations.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/service/openai_gateway.py`
- Modify: `plugin/trusted-ceo-agent/schemas/reasoning-job.schema.json`
- Modify: `tests/unit/reasoning/test_jobs.py`
- Modify: `tests/unit/service/test_openai_gateway.py`

- [ ] **Step 1: Write RED tests for exact context/allowlist matching and limits**

Add job tests using two document items and one fact. Assert the lens compiler
puts at most 48 combined work items in a shard, keeps only the shard's document
contexts, and preserves `job_id` for a legacy no-document fixture.

Add explicit failure cases:

```python
with self.assertRaisesRegex(ContractError, "context IDs must match"):
    build_reasoning_job(
        **lens_fields,
        allowed_document_evidence_ids=["document_" + "a" * 24],
        document_evidence_context=[document_b],
    )

with self.assertRaisesRegex(ContractError, "96,000"):
    build_reasoning_job(
        **lens_fields,
        allowed_document_evidence_ids=[item["document_evidence_id"] for item in contexts],
        document_evidence_context=contexts,
    )
```

In gateway tests, mutate a context after job creation and assert the transport is
not called. Also assert the actual request contains document text, its ID appears
in `untrusted_text_markers`, `store` is false, and no tools are supplied.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.reasoning.test_jobs tests.unit.service.test_openai_gateway -q
```

Expected: FAIL because reasoning jobs do not accept or carry Document Evidence.

- [ ] **Step 3: Implement optional lens-only context and combined sharding**

Add optional fields without emitting them for empty/legacy jobs:

```python
MAX_JOB_ITEMS = 48
MAX_DOCUMENT_CONTEXT_CHARACTERS = 96_000

def _document_context(fields: Mapping[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    identifiers = _sorted_unique(
        fields.get("allowed_document_evidence_ids"),
        "allowed_document_evidence_ids",
    )
    contexts = [dict(item) for item in fields.get("document_evidence_context", [])]
    context_ids = [str(item.get("document_evidence_id", "")) for item in contexts]
    if context_ids != sorted(context_ids) or set(context_ids) != set(identifiers):
        raise ContractError("document context IDs must match their allowlist")
    if sum(len(str(item.get("content", ""))) for item in contexts) > MAX_DOCUMENT_CONTEXT_CHARACTERS:
        raise ContractError("document context exceeds 96,000 characters")
    for item in contexts:
        SchemaStore().validate("document-evidence.schema.json", item)
    return identifiers, contexts
```

Reject document fields on non-lens stages. For lens jobs with documents, add
both fields and add every ID to `untrusted_text_markers`. Include them in the
job ID hash. For no-document jobs, do not add keys so existing canonical bytes
and IDs remain unchanged.

Build lens work items as tagged records:

```python
work_items = [
    {"id": item["fact_id"], "kind": "fact", "scope": item.get("scope", []), "period": item.get("time_context", {})}
    for item in facts
] + [
    {"id": item["document_evidence_id"], "kind": "document", "context": item, "scope": item.get("logical_path", ""), "period": item.get("line_start", 0)}
    for item in document_evidence
]
```

Each 48-item shard separates Fact IDs from Document Evidence contexts before
calling `build_reasoning_job`. Keep the existing six-shard failure and map it to
`scope_narrowing_required`; never slice off excess contexts.

Immediately before transport, the gateway rebuilds and schema-validates the job,
revalidates context hashes/limits, and sends the canonical job JSON as the only
user input. Retain the system rule that uploaded content is data, never instructions.

- [ ] **Step 4: Run focused GREEN tests**

Run the Step 2 command again.

Expected: PASS; legacy IDs are stable, document jobs are bounded, tampering stops before transport, and all text is marked untrusted.

- [ ] **Step 5: Commit Task 7**

```powershell
git add -- plugin/trusted-ceo-agent/trusted_ceo_agent/reasoning/jobs.py plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutations.py plugin/trusted-ceo-agent/trusted_ceo_agent/service/openai_gateway.py plugin/trusted-ceo-agent/schemas/reasoning-job.schema.json tests/unit/reasoning/test_jobs.py tests/unit/service/test_openai_gateway.py
git commit -m "feat: provide bounded markdown context to lens jobs"
```

## Task 8: Model result validators accept only allowed Document Evidence

**Files:**
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/reasoning/ref_validation.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/reasoning/normalizer.py`
- Modify: `plugin/trusted-ceo-agent/schemas/lens-card-draft.schema.json`
- Modify: `plugin/trusted-ceo-agent/schemas/normalized-card.schema.json`
- Modify: `tests/unit/reasoning/test_join_and_drafts.py`
- Modify: `tests/unit/reasoning/test_normalizer.py`
- Modify: `tests/unit/evidence/test_evidence_builders.py`

- [ ] **Step 1: Write RED tests for valid and invalid document citations**

Create one lens job whose allowlist contains `document_a`. Make a material claim
with `evidence_proposals: [{evidence_ref: document_a, polarity: "supports", role:
"corroboration"}]` and an observation with `document_evidence_ids: [document_a]`.
Assert normalization produces:

```python
self.assertEqual([document_a], card["used_document_evidence_ids"])
self.assertEqual("document", card["evidence_links"][0]["evidence_kind"])
self.assertEqual(document_a, card["evidence_links"][0]["evidence_ref"])
```

Add cases where the draft cites a document from another shard, an unknown
document, or uses a document ID in `value_refs[].fact_or_signal_id`; each must
raise `ContractError`. Add an Evidence Core test where a document link points to
an absent register item and assert `IntegrityError`.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.reasoning.test_join_and_drafts tests.unit.reasoning.test_normalizer tests.unit.evidence.test_evidence_builders -q
```

Expected: FAIL because schemas, ref collection, normalized cards, and Evidence Links only accept Fact/Signal evidence.

- [ ] **Step 3: Extend reference validation without weakening value references**

Add `document_evidence_ids` as an optional unique string set on lens
observations and `used_document_evidence_ids` on normalized cards. Keep all
existing Fact/Signal fields required and backward-compatible defaults empty.

In ref validation, build three allowlists:

```python
facts = _job_set(job, "allowed_fact_ids")
signals = _job_set(job, "allowed_signal_ids")
documents = _job_set(job, "allowed_document_evidence_ids")
evidence = facts | signals | documents
```

Use `evidence` for `evidence_proposals[].evidence_ref`. Use only `facts |
signals` for `value_refs[].fact_or_signal_id`, test results, and numeric display
tokens. Validate observation `document_evidence_ids` against `documents`.

Change `_collect_refs` to return `(used_facts, used_signals, used_documents)`.
When materializing a link, set kind by prefix:

```python
evidence_kind = (
    "fact" if evidence_ref.startswith("fact_")
    else "signal" if evidence_ref.startswith("signal_")
    else "document"
)
```

Add sorted `used_document_evidence_ids` to the normalized card. In
`EvidenceCoreValidator`, resolve `evidence_kind=document` only against the
document register and verify its Source lineage. Preserve Signal-specific
polarity rules only for Signal links.

- [ ] **Step 4: Run focused GREEN and contract tests**

Run sequentially:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.reasoning.test_join_and_drafts tests.unit.reasoning.test_normalizer tests.unit.evidence.test_evidence_builders -q
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.contracts.test_reasoning_grading_hitl_schemas tests.contracts.test_core_evidence_schemas -q
```

Expected: PASS; allowed document claims work, cross-shard/unknown references fail, and documents cannot substitute for numeric values.

- [ ] **Step 5: Commit Task 8**

```powershell
git add -- plugin/trusted-ceo-agent/trusted_ceo_agent/reasoning/ref_validation.py plugin/trusted-ceo-agent/trusted_ceo_agent/reasoning/normalizer.py plugin/trusted-ceo-agent/schemas/lens-card-draft.schema.json plugin/trusted-ceo-agent/schemas/normalized-card.schema.json tests/unit/reasoning/test_join_and_drafts.py tests/unit/reasoning/test_normalizer.py tests/unit/evidence/test_evidence_builders.py
git commit -m "feat: validate markdown citations in model results"
```

## Task 9: End-to-end service and browser regression

**Files:**
- Modify: `tests/unit/service/test_app.py`
- Modify: `tests/unit/service/test_orchestrator_context.py`
- Modify: `web/tests/e2e/analysis-ai-service.spec.ts`
- Modify: `web/README.md`

- [ ] **Step 1: Write the integration RED scenarios**

Add a Python service test that uploads `전략/plan.md` and `data.csv` in separate
batches, checks the canonical two-path snapshot, advances to lens job creation,
and asserts at least one job contains the exact Markdown text and allowed
document ID.

Extend the Playwright service scenario to:

1. Upload one Markdown file through the file picker.
2. Simulate a directory `폴더B/sub/data.csv` through `setInputFiles` and a
   `webkitRelativePath` property in the page context.
3. Verify both `개별 파일` and `폴더B` groups remain visible.
4. Reload and verify the same canonical groups return from the service.
5. Start analysis and verify both upload controls disable.

- [ ] **Step 2: Run focused integration tests and verify RED**

Run one at a time:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.service.test_app tests.unit.service.test_orchestrator_context -q
npm --prefix web run test:e2e -- analysis-ai-service.spec.ts
```

Expected: the newly added assertions FAIL until the complete service/browser path is connected.

- [ ] **Step 3: Connect missing boundaries and document usage**

Make only the minimal integration fixes exposed by Step 2. Update `web/README.md`
to state:

```markdown
분석 자료는 CSV, JSON, XLSX, Markdown을 지원합니다. 파일 선택은 여러 번
누적할 수 있고, 폴더 선택은 하위 지원 파일을 재귀적으로 추가합니다. 화면에는
선택 루트 기준 논리 상대경로만 표시되며 절대경로는 전송되지 않습니다.
Markdown은 비신뢰 문서 근거로 구간화되어 허용된 lens Job에만 전달됩니다.
```

- [ ] **Step 4: Run integration GREEN tests**

Run the Step 2 commands again, one at a time.

Expected: Python integration PASS and the targeted Playwright spec PASS without reading `.env.local` in test output.

- [ ] **Step 5: Commit Task 9**

```powershell
git add -- tests/unit/service/test_app.py tests/unit/service/test_orchestrator_context.py web/tests/e2e/analysis-ai-service.spec.ts web/README.md
git commit -m "test: cover markdown folder upload flow"
```

## Task 10: Full completion gate and final audit

**Files:**
- No planned production edits.
- Update tests or implementation only if a gate exposes a regression caused by this feature.

- [ ] **Step 1: Inspect the final change boundary**

Run:

```powershell
git status --short --branch
git diff --stat b0b1b97..HEAD
git diff --name-only b0b1b97..HEAD
```

Expected: only feature files and the approved design/plan commits are present in the feature commit range. User-owned pre-existing changes remain unstaged and unmodified.

- [ ] **Step 2: Run contract checks**

Run one at a time:

```powershell
npm --prefix contracts/web-report run check
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.contracts.test_core_evidence_schemas tests.contracts.test_reasoning_grading_hitl_schemas tests.contracts.test_web_report_contract_schemas -q
```

Expected: both commands exit 0.

- [ ] **Step 3: Run the full Python gate once**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest discover -s tests -q
```

Expected: all Python tests PASS; the previous 605-test baseline grows by the new tests.

- [ ] **Step 4: Run web gates sequentially**

Run one at a time:

```powershell
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web run test
npm --prefix web run build
npm --prefix web run test:e2e
```

Expected: typecheck, lint, Vitest plus the 10 launcher tests, production build, and all Playwright tests exit 0. The previous 181 Vitest and 3 Playwright baselines grow by the new coverage.

- [ ] **Step 5: Re-run only gates affected by any post-gate fix**

If a gate requires a code change, write a focused failing regression test first,
make the minimum fix, run that focused test, then rerun only the affected full
gate. Do not repeat unchanged successful gates.

- [ ] **Step 6: Final source and secret audit**

Run:

```powershell
git diff --check b0b1b97..HEAD
git status --short --branch
git diff --name-only b0b1b97..HEAD
```

Confirm manually from the name list that `.env.local`, recovery backups, user
changes, and unrelated evaluation artifacts are absent. Do not print secret
file contents.

- [ ] **Step 7: Commit any gate-only regression fix**

If Step 5 produced a tested fix, stage only its named test and implementation
files and commit:

```powershell
git commit -m "fix: close markdown upload regression"
```

If no fix was needed, do not create an empty commit.

## Plan self-review result

- Spec coverage: upload accumulation, folder recursion, logical relative paths,
  Markdown validation/chunking, first-class evidence, bounded model context,
  result validation, Source lineage, backward compatibility, replay behavior,
  and all completion gates map to Tasks 1–10.
- Type consistency: `AnalysisUpload`, `UploadedFileSummary`, `logical_paths`,
  `SourceUpload.logical_path`, `document_evidence_register`,
  `allowed_document_evidence_ids`, and `document_evidence_context` use the same
  names at every boundary.
- Security consistency: logical paths are display data only; absolute/private
  paths and secrets never enter public snapshots or model jobs.
- No silent truncation: the 48-item, 96,000-character, and six-shard limits
  produce `scope_narrowing_required` instead of dropping document chunks.
