"use client";

import { useEffect, useRef, useState } from "react";

import {
  formatFileSize,
  type AnalysisUpload,
  type UploadedFileSummary,
} from "@/features/analysis/analysis-model";
import { normalizeUploadSelection } from '@/features/analysis/upload-selection';

type DataUploadCardProps = {
  disabled?: boolean;
  files: UploadedFileSummary[];
  mode?: "replay" | "service";
  onUploadsSelected: (uploads: AnalysisUpload[]) => Promise<void>;
};

export function DataUploadCard({
  disabled = false,
  files,
  mode = "replay",
  onUploadsSelected,
}: DataUploadCardProps) {
  const [error, setError] = useState<string | null>(null);
  const [skippedCount, setSkippedCount] = useState(0);
  const folderInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    folderInputRef.current?.setAttribute('webkitdirectory', '');
    folderInputRef.current?.setAttribute('directory', '');
  }, []);

  async function handleFiles(
    selectedFiles: Iterable<File>,
    mode: 'files' | 'folder',
  ) {
    try {
      const selection = normalizeUploadSelection(selectedFiles, mode);
      setSkippedCount(selection.skippedCount);
      if (selection.uploads.length === 0) {
        setError(selection.skippedCount > 0
          ? '폴더에 지원되는 분석 파일이 없습니다.'
          : null);
        return;
      }
      setError(null);
      await onUploadsSelected(selection.uploads);
    } catch (caught) {
      setError(caught instanceof Error
        ? caught.message
        : '자료를 업로드하지 못했습니다. 파일 정책과 서비스 상태를 확인해 주세요.');
    }
  }

  const groups = new Map<string, UploadedFileSummary[]>();
  for (const file of files) {
    const group = groups.get(file.collection_label) ?? [];
    group.push(file);
    groups.set(file.collection_label, group);
  }

  return (
    <section className="data-upload-card">
      <div className="panel-heading">
        <p className="eyebrow">입력 자료</p>
        <h2>업로드 자료</h2>
      </div>
      <div className="upload-choice-grid">
        <label className="file-drop" data-disabled={disabled} htmlFor="analysis-file-input">
          <span className="file-drop-icon" aria-hidden="true">+</span>
          <span>
            <strong>분석 자료 선택</strong>
            <small>CSV · JSON · XLSX · MD</small>
          </span>
          <input
            aria-label="분석 자료 선택"
            accept=".csv,.json,.xlsx,.md"
            disabled={disabled}
            id="analysis-file-input"
            multiple
            onChange={(event) => {
              const selected = Array.from(event.currentTarget.files ?? []);
              event.currentTarget.value = '';
              void handleFiles(selected, 'files');
            }}
            type="file"
          />
        </label>
        <label className="file-drop" data-disabled={disabled} htmlFor="analysis-folder-input">
          <span className="file-drop-icon" aria-hidden="true">↥</span>
          <span>
            <strong>분석 폴더 선택</strong>
            <small>하위 폴더까지 한 번에 추가</small>
          </span>
          <input
            aria-label="분석 폴더 선택"
            disabled={disabled}
            id="analysis-folder-input"
            multiple
            onChange={(event) => {
              const selected = Array.from(event.currentTarget.files ?? []);
              event.currentTarget.value = '';
              void handleFiles(selected, 'folder');
            }}
            ref={folderInputRef}
            type="file"
          />
        </label>
      </div>
      <p className="upload-boundary">
        {mode === "service"
          ? "파일은 localhost 서비스로 전송되어 형식·크기·내용 안전성 검사를 받습니다."
          : "저장된 시연에서는 파일명·형식·크기만 보존하며 내용은 읽지 않습니다."}
      </p>
      {skippedCount > 0 ? (
        <p className="upload-status" role="status">
          지원하지 않는 폴더 파일 {skippedCount}개를 건너뛰었습니다.
        </p>
      ) : null}
      {error ? <p className="inline-error" role="alert">{error}</p> : null}
      {files.length ? (
        <div className="file-groups" aria-label="업로드한 자료">
          {Array.from(groups).map(([label, group]) => (
            <section className="file-group" key={label}>
              <h3>{label}</h3>
              <ul className="file-list">
                {group.map((file) => (
                  <li key={file.logical_path}>
                    <span aria-hidden="true" className="file-kind">
                      {file.display_name.split('.').pop()?.toUpperCase()}
                    </span>
                    <span>
                      <strong>{file.logical_path}</strong>
                      <small>{formatFileSize(file.size_bytes)}</small>
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      ) : (
        <p className="empty-note">아직 선택한 자료가 없습니다.</p>
      )}
    </section>
  );
}
