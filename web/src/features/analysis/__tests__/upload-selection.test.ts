import { describe, expect, it } from 'vitest';

import { normalizeUploadSelection } from '@/features/analysis/upload-selection';

function withRelativePath(file: File, path: string): File {
  Object.defineProperty(file, 'webkitRelativePath', { value: path });
  return file;
}

describe('normalizeUploadSelection', () => {
  it('keeps supported files recursively and reports skipped folder files', () => {
    const markdown = withRelativePath(
      new File(['# Plan'], 'plan.md', { type: 'text/markdown' }),
      'strategy/2026/plan.md',
    );
    const executable = withRelativePath(
      new File(['x'], 'run.exe', { type: 'application/octet-stream' }),
      'strategy/bin/run.exe',
    );

    expect(normalizeUploadSelection([markdown, executable], 'folder')).toEqual({
      uploads: [{
        file: markdown,
        logicalPath: 'strategy/2026/plan.md',
        collectionLabel: 'strategy',
      }],
      skippedCount: 1,
    });
  });

  it('rejects unsafe browser relative paths', () => {
    const file = withRelativePath(
      new File(['# bad'], 'bad.md', { type: 'text/markdown' }),
      '../bad.md',
    );

    expect(() => normalizeUploadSelection([file], 'folder')).toThrow(
      '안전하지 않은 폴더 경로',
    );
  });

  it('accepts case-insensitive Markdown files in file mode', () => {
    const file = new File(['# Plan'], 'PLAN.MD', { type: '' });

    expect(normalizeUploadSelection([file], 'files')).toEqual({
      uploads: [{
        file,
        logicalPath: 'PLAN.MD',
        collectionLabel: '개별 파일',
      }],
      skippedCount: 0,
    });
  });
});
