export const MAX_REPORT_IMPORT_BYTES = 50 * 1024 * 1024;
export const REPORT_BUNDLE_FILE_NAME = "web-report-bundle.json";
export const REPORT_FILE_NAME_HEADER = "x-trusted-ceo-file-name";

export type ReportImportMetadata = Readonly<{
  fileName: string;
  contentType: string;
  contentLength: number;
}>;

export class ReportImportPolicyError extends Error {
  constructor(
    message: string,
    readonly status: 400 | 413 | 415,
  ) {
    super(message);
    this.name = "ReportImportPolicyError";
  }
}

export function assertReportImport(metadata: ReportImportMetadata): void {
  if (
    metadata.fileName !== REPORT_BUNDLE_FILE_NAME ||
    metadata.fileName.includes("/") ||
    metadata.fileName.includes("\\")
  ) {
    throw new ReportImportPolicyError(
      "결과 리포트에는 web-report-bundle.json 한 파일만 가져올 수 있습니다.",
      415,
    );
  }
  if (metadata.contentType !== "application/json") {
    throw new ReportImportPolicyError(
      "결과 리포트의 형식은 application/json이어야 합니다.",
      415,
    );
  }
  if (
    !Number.isSafeInteger(metadata.contentLength) ||
    metadata.contentLength <= 0
  ) {
    throw new ReportImportPolicyError(
      "결과 리포트의 크기를 확인할 수 없습니다.",
      400,
    );
  }
  if (metadata.contentLength > MAX_REPORT_IMPORT_BYTES) {
    throw new ReportImportPolicyError(
      "결과 리포트는 50 MiB를 넘을 수 없습니다.",
      413,
    );
  }
}

export function reportImportMetadataFromHeaders(
  headers: Headers,
): ReportImportMetadata {
  const rawLength = headers.get("content-length");
  if (rawLength === null || !/^[0-9]+$/.test(rawLength)) {
    throw new ReportImportPolicyError(
      "결과 리포트의 크기를 확인할 수 없습니다.",
      400,
    );
  }
  const metadata = {
    fileName: headers.get(REPORT_FILE_NAME_HEADER) ?? "",
    contentType: headers.get("content-type") ?? "",
    contentLength: Number(rawLength),
  };
  assertReportImport(metadata);
  return metadata;
}

export async function readRequestBodyWithinLimit(
  stream: ReadableStream<Uint8Array> | null,
  maximumBytes = MAX_REPORT_IMPORT_BYTES,
): Promise<Uint8Array> {
  if (stream === null) {
    throw new ReportImportPolicyError(
      "결과 리포트 파일이 비어 있습니다.",
      400,
    );
  }
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      total += value.byteLength;
      if (total > maximumBytes) {
        await reader.cancel();
        throw new ReportImportPolicyError(
          "결과 리포트는 50 MiB를 넘을 수 없습니다.",
          413,
        );
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  if (total === 0) {
    throw new ReportImportPolicyError(
      "결과 리포트 파일이 비어 있습니다.",
      400,
    );
  }
  const result = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result;
}
