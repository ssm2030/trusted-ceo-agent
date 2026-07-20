"use client";

import { useState } from "react";

import {
  formatFileSize,
  type ReplayFileMetadata,
} from "@/features/analysis/analysis-model";
import { validateReplayFile } from "@/features/analysis/replay-provider";

type DataUploadCardProps = {
  disabled?: boolean;
  files: ReplayFileMetadata[];
  mode?: "replay" | "service";
  onFilesSelected: (files: File[]) => Promise<void>;
};

export function DataUploadCard({
  disabled = false,
  files,
  mode = "replay",
  onFilesSelected,
}: DataUploadCardProps) {
  const [error, setError] = useState<string | null>(null);

  async function handleFiles(fileList: FileList | null) {
    const nextFiles = Array.from(fileList ?? []);
    const invalid = nextFiles
      .map((file) => validateReplayFile(file))
      .find((result) => !result.accepted);

    if (invalid && !invalid.accepted) {
      setError(invalid.message);
      return;
    }
    if (nextFiles.length === 0) return;

    setError(null);
    try {
      await onFilesSelected(nextFiles);
    } catch {
      setError("자료를 업로드하지 못했습니다. 파일 정책과 서비스 상태를 확인해 주세요.");
    }
  }

  return (
    <section className="data-upload-card">
      <div className="panel-heading">
        <p className="eyebrow">입력 자료</p>
        <h2>업로드 자료</h2>
      </div>
      <label className="file-drop" data-disabled={disabled} htmlFor="analysis-file-input">
        <span className="file-drop-icon" aria-hidden="true">+</span>
        <span>
          <strong>분석 자료 선택</strong>
          <small>CSV · JSON · XLSX</small>
        </span>
        <input
          aria-label="분석 자료 선택"
          accept=".csv,.json,.xlsx"
          disabled={disabled}
          id="analysis-file-input"
          multiple
          onChange={(event) => void handleFiles(event.target.files)}
          type="file"
        />
      </label>
      <p className="upload-boundary">
        {mode === "service"
          ? "파일은 localhost 서비스로 전송되어 형식·크기·내용 안전성 검사를 받습니다."
          : "저장된 시연에서는 파일명·형식·크기만 보존하며 내용은 읽지 않습니다."}
      </p>
      {error ? <p className="inline-error" role="alert">{error}</p> : null}
      {files.length ? (
        <ul className="file-list" aria-label="선택한 자료">
          {files.map((file, index) => (
            <li key={`${file.name}-${file.size}-${index}`}>
              <span aria-hidden="true" className="file-kind">
                {file.name.split(".").pop()?.toUpperCase()}
              </span>
              <span>
                <strong>{file.name}</strong>
                <small>{formatFileSize(file.size)}</small>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty-note">아직 선택한 자료가 없습니다.</p>
      )}
    </section>
  );
}