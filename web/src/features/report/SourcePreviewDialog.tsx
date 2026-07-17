"use client";

import {
  useEffect,
  useId,
  useState,
  type RefObject,
} from "react";

import type { SourcePreviewResponse } from "@/features/report/report-model";
import styles from "@/features/report/ReportWorkspace.module.css";

type LoadPreview = (
  previewRef: string,
  signal?: AbortSignal,
) => Promise<SourcePreviewResponse>;

type SourcePreviewDialogProps = {
  loadPreview?: LoadPreview;
  onClose: () => void;
  open: boolean;
  previewRef: string | null;
  returnFocusRef?: RefObject<HTMLElement | null>;
  sourceName: string;
};

async function loadPreviewFromServer(
  previewRef: string,
  signal?: AbortSignal,
): Promise<SourcePreviewResponse> {
  const response = await fetch(
    `/api/report/source-previews/${encodeURIComponent(previewRef)}`,
    {
      cache: "no-store",
      signal,
    },
  );
  if (!response.ok) {
    throw new Error("출처 미리보기를 불러오지 못했습니다.");
  }
  return (await response.json()) as SourcePreviewResponse;
}

export function SourcePreviewDialog({
  loadPreview = loadPreviewFromServer,
  onClose,
  open,
  previewRef,
  returnFocusRef,
  sourceName,
}: SourcePreviewDialogProps) {
  const titleId = useId();
  const [result, setResult] = useState<{
    previewRef: string;
    preview: SourcePreviewResponse | null;
    error: string | null;
  }>({ previewRef: "", preview: null, error: null });

  useEffect(() => {
    if (!open || previewRef === null) {
      return;
    }

    const controller = new AbortController();
    void loadPreview(previewRef, controller.signal)
      .then((preview) => {
        setResult({ previewRef, preview, error: null });
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setResult({
          previewRef,
          preview: null,
          error:
            cause instanceof Error
              ? cause.message
              : "출처 미리보기를 불러오지 못했습니다.",
        });
      });

    return () => controller.abort();
  }, [loadPreview, open, previewRef]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") {
        return;
      }
      onClose();
      returnFocusRef?.current?.focus();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open, returnFocusRef]);

  if (!open || previewRef === null) {
    return null;
  }

  const closeDialog = () => {
    onClose();
    returnFocusRef?.current?.focus();
  };
  const currentResult = result.previewRef === previewRef ? result : null;
  const loading = currentResult === null;
  const preview = currentResult?.preview ?? null;
  const error = currentResult?.error ?? null;

  return (
    <div className={styles.dialogBackdrop}>
      <section
        aria-labelledby={titleId}
        aria-modal="true"
        className={styles.dialog}
        role="dialog"
      >
        <header className={styles.dialogHeader}>
          <div>
            <p className={styles.sectionKicker}>출처 미리보기</p>
            <h2 id={titleId}>{sourceName} 미리보기</h2>
          </div>
          <button
            aria-label="출처 미리보기 닫기"
            autoFocus
            className={styles.closeButton}
            onClick={closeDialog}
            type="button"
          >
            닫기
          </button>
        </header>

        <div className={styles.dialogBody}>
          {loading ? <p>미리보기를 불러오고 있습니다.</p> : null}
          {error === null ? null : (
            <p className={styles.tableFallback} role="alert">
              {error}
            </p>
          )}
          {preview === null ? null : preview.access_policy === "permitted" ? (
            <>
              <p className={styles.dialogNotice}>
                {preview.locator_summary}
                {preview.truncated ? " · 일부 행만 표시" : ""}
              </p>
              <div className={styles.dialogTableWrap}>
                <table className={styles.dialogTable}>
                  <thead>
                    <tr>
                      {preview.column_labels.map((label, index) => (
                        <th key={`${label}:${index}`} scope="col">
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, rowIndex) => (
                      <tr key={`preview-row:${rowIndex}`}>
                        {row.map((cell, cellIndex) => (
                          <td key={`preview-cell:${rowIndex}:${cellIndex}`}>
                            {cell === null ? "—" : String(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className={styles.dialogNotice}>{preview.message}</p>
          )}
        </div>
      </section>
    </div>
  );
}
