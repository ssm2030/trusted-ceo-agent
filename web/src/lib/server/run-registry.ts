import { readFile, realpath } from "node:fs/promises";
import path from "node:path";

export type RunRegistration = Readonly<{
  registration_id: string;
  canonical_artifact_root: string;
  expected_run_id: string;
  allowed_revision: number;
  expected_bundle_hash: string;
}>;

const REGISTRATION_KEYS = [
  "allowed_revision",
  "canonical_artifact_root",
  "expected_bundle_hash",
  "expected_run_id",
  "registration_id",
] as const;
const REGISTRATION_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const RUN_ID_PATTERN =
  /^run_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{16}$/;
const HASH_PATTERN = /^[0-9a-f]{64}$/;

export class RunRegistryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RunRegistryError";
  }
}

function isPlainObject(
  value: unknown,
): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function assertExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): void {
  const actual = Object.keys(value).sort();
  if (
    actual.length !== expected.length ||
    actual.some((key, index) => key !== expected[index])
  ) {
    throw new RunRegistryError("실행 등록 정보의 필드가 올바르지 않습니다.");
  }
}

function remainsWithin(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return (
    relative === "" ||
    (!relative.startsWith(`..${path.sep}`) &&
      relative !== ".." &&
      !path.isAbsolute(relative))
  );
}

export class RunRegistry {
  constructor(
    private readonly registryPath: string,
    private readonly allowlistRoot: string,
  ) {
    if (
      !path.isAbsolute(registryPath) ||
      !path.isAbsolute(allowlistRoot)
    ) {
      throw new RunRegistryError(
        "실행 registry 경로는 서버의 절대 경로여야 합니다.",
      );
    }
  }

  private async load(): Promise<Map<string, RunRegistration>> {
    const [serialized, allowedRoot] = await Promise.all([
      readFile(this.registryPath, "utf8"),
      realpath(this.allowlistRoot),
    ]);
    let document: unknown;
    try {
      document = JSON.parse(serialized) as unknown;
    } catch {
      throw new RunRegistryError("실행 registry JSON이 올바르지 않습니다.");
    }
    if (!isPlainObject(document)) {
      throw new RunRegistryError("실행 registry 형식이 올바르지 않습니다.");
    }
    assertExactKeys(document, ["registrations"]);
    if (!Array.isArray(document.registrations)) {
      throw new RunRegistryError("실행 registry 형식이 올바르지 않습니다.");
    }

    const registrations = new Map<string, RunRegistration>();
    for (const rawRegistration of document.registrations) {
      if (!isPlainObject(rawRegistration)) {
        throw new RunRegistryError(
          "실행 등록 정보의 형식이 올바르지 않습니다.",
        );
      }
      assertExactKeys(rawRegistration, REGISTRATION_KEYS);
      const {
        registration_id: registrationId,
        canonical_artifact_root: artifactRoot,
        expected_run_id: expectedRunId,
        allowed_revision: allowedRevision,
        expected_bundle_hash: expectedBundleHash,
      } = rawRegistration;
      if (
        typeof registrationId !== "string" ||
        !REGISTRATION_ID_PATTERN.test(registrationId) ||
        typeof artifactRoot !== "string" ||
        !path.isAbsolute(artifactRoot) ||
        typeof expectedRunId !== "string" ||
        !RUN_ID_PATTERN.test(expectedRunId) ||
        typeof allowedRevision !== "number" ||
        !Number.isInteger(allowedRevision) ||
        allowedRevision < 1 ||
        typeof expectedBundleHash !== "string" ||
        !HASH_PATTERN.test(expectedBundleHash)
      ) {
        throw new RunRegistryError(
          "실행 등록 정보의 값이 올바르지 않습니다.",
        );
      }
      if (registrations.has(registrationId)) {
        throw new RunRegistryError(
          "중복된 실행 registration_id가 있습니다.",
        );
      }
      const canonicalArtifactRoot = await realpath(artifactRoot);
      if (!remainsWithin(allowedRoot, canonicalArtifactRoot)) {
        throw new RunRegistryError(
          "artifact root가 허용된 실행 디렉터리 밖에 있습니다.",
        );
      }
      registrations.set(
        registrationId,
        Object.freeze({
          registration_id: registrationId,
          canonical_artifact_root: canonicalArtifactRoot,
          expected_run_id: expectedRunId,
          allowed_revision: allowedRevision,
          expected_bundle_hash: expectedBundleHash,
        }),
      );
    }
    return registrations;
  }

  async get(registrationId: string): Promise<RunRegistration> {
    if (!REGISTRATION_ID_PATTERN.test(registrationId)) {
      throw new RunRegistryError("실행 registration_id가 올바르지 않습니다.");
    }
    const registration = (await this.load()).get(registrationId);
    if (registration === undefined) {
      throw new RunRegistryError("등록된 실행을 찾을 수 없습니다.");
    }
    return registration;
  }
}
