"use client";

import { useState } from "react";

import {
  formatFileSize,
  type ReplayFileMetadata,
} from "@/features/analysis/analysis-model";
import { validateReplayFile } from "@/features/analysis/replay-provider";

type DataUploadCardProps = {
  files: ReplayFileMetadata[];
  onFilesSelected: (files: File[]) => Promise<void>;
};

export function DataUploadCard({
  files,
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
    if (nextFiles.length === 0) {
      return;
    }

    setError(null);
    await onFilesSelected(nextFiles);
  }

  return (
    <section className="data-upload-card">
      <div className="panel-heading">
        <p className="eyebrow">입력 자료</p>
        <h2>업로드 자료</h2>
      </div>
      <label className="file-drop" htmlFor="analysis-file-input">
        <span className="file-drop-icon" aria-hidden="true">
          +
        </span>
        <span>
          <strong>분석 자료 선택</strong>
          <small>CSV · JSON · XLSX</small>
        </span>
        <input
          aria-label="분석 자료 선택"
          accept=".csv,.json,.xlsx"
          id="analysis-file-input"
          multiple
          onChange={(event) => void handleFiles(event.target.files)}
          type="file"
        />
      </label>
      <p className="upload-boundary">
        replay에서는 파일명·형식·크기만 보존하며 내용은 읽지 않습니다.
      </p>
      {error ? (
        <p className="inline-error" role="alert">
          {error}
        </p>
      ) : null}
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
