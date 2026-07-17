"use client";

import { useState, type ChangeEvent } from "react";

import styles from "@/features/report/ReportWorkspace.module.css";

const EXPECTED_FILE_NAME = "web-report-bundle.json";
const MAX_FILE_BYTES = 50 * 1024 * 1024;

type ReportImportControlProps = {
  csrfToken: string | null;
  hasCurrentReport: boolean;
  onImported: () => Promise<void>;
};

type ImportStatus =
  | { kind: "idle"; message: null }
  | { kind: "error" | "success"; message: string };

function retainedSuffix(hasCurrentReport: boolean): string {
  return hasCurrentReport ? " 기존 결과는 유지됩니다." : "";
}

function importErrorMessage(
  status: number,
  hasCurrentReport: boolean,
): string {
  const retained = retainedSuffix(hasCurrentReport);
  switch (status) {
    case 400:
      return `요청 형식을 확인해 주세요.${retained}`;
    case 401:
      return `로컬 세션이 만료되었습니다. 페이지를 새로고침해 주세요.${retained}`;
    case 403:
      return `로컬 보안 검사를 통과하지 못했습니다.${retained}`;
    case 413:
      return `파일은 50 MiB 이하여야 합니다.${retained}`;
    case 415:
      return `web-report-bundle.json 형식만 가져올 수 있습니다.${retained}`;
    case 422:
      return `묶음 검증에 실패했습니다.${retained}`;
    default:
      return `리포트를 가져오지 못했습니다.${retained}`;
  }
}

export function ReportImportControl({
  csrfToken,
  hasCurrentReport,
  onImported,
}: ReportImportControlProps) {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [status, setStatus] = useState<ImportStatus>({
    kind: "idle",
    message: null,
  });

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.currentTarget.files?.[0] ?? null;
    setFile(selected);
    setStatus({ kind: "idle", message: null });
    if (selected === null) {
      setFileError(null);
      return;
    }
    if (selected.name !== EXPECTED_FILE_NAME) {
      setFileError(
        `파일 이름은 ${EXPECTED_FILE_NAME}이어야 합니다.`,
      );
      return;
    }
    if (selected.size > MAX_FILE_BYTES) {
      setFileError("파일은 50 MiB 이하여야 합니다.");
      return;
    }
    setFileError(null);
  };

  const importReport = async () => {
    if (file === null || fileError !== null || csrfToken === null) {
      return;
    }
    setImporting(true);
    setStatus({ kind: "idle", message: null });
    try {
      const response = await fetch("/api/report/import", {
        body: file,
        headers: {
          "Content-Type": "application/json",
          "x-csrf-token": csrfToken,
          "x-trusted-ceo-file-name": EXPECTED_FILE_NAME,
        },
        method: "POST",
      });
      if (!response.ok) {
        setStatus({
          kind: "error",
          message: importErrorMessage(response.status, hasCurrentReport),
        });
        return;
      }
      await onImported();
      setStatus({
        kind: "success",
        message: "검증된 결과로 교체했습니다.",
      });
    } catch {
      setStatus({
        kind: "error",
        message: `리포트를 가져오지 못했습니다.${retainedSuffix(
          hasCurrentReport,
        )}`,
      });
    } finally {
      setImporting(false);
    }
  };

  return (
    <section aria-labelledby="report-import-title" className={styles.sourceCard}>
      <div>
        <p className={styles.sectionKicker}>로컬 JSON 가져오기</p>
        <h2 className={styles.evidenceHeading} id="report-import-title">
          검증할 웹 리포트 선택
        </h2>
        <p className={styles.metricMeta}>
          JSON 단일 파일만 전송하며, 검증에 실패하면 현재 결과를 바꾸지
          않습니다.
        </p>
      </div>
      <div className={styles.sourceActions}>
        <label className="file-drop">
          <span aria-hidden="true" className="file-drop-icon">↥</span>
          <span>
            <strong>웹 리포트 JSON 파일</strong>
            <small>web-report-bundle.json · 최대 50 MiB</small>
          </span>
          <input
            accept=".json,application/json"
            aria-label="웹 리포트 JSON 파일"
            disabled={importing}
            onChange={handleFileChange}
            type="file"
          />
        </label>
        <button
          className={styles.actionButton}
          disabled={
            importing ||
            csrfToken === null ||
            file === null ||
            fileError !== null
          }
          onClick={() => void importReport()}
          type="button"
        >
          {importing ? "검증 중" : "리포트 가져오기"}
        </button>
      </div>
      {csrfToken === null ? (
        <p className={styles.notice}>로컬 세션을 준비할 수 없습니다.</p>
      ) : null}
      {fileError === null ? null : (
        <p className={styles.tableFallback} role="alert">
          {fileError}
        </p>
      )}
      {status.message === null ? null : (
        <p
          className={
            status.kind === "success" ? styles.notice : styles.tableFallback
          }
          role={status.kind === "error" ? "alert" : "status"}
        >
          {status.message}
        </p>
      )}
    </section>
  );
}
