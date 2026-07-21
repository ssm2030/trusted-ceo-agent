import type { AnalysisUpload } from '@/features/analysis/analysis-model';
import { normalizeUploadLogicalPath } from '@/lib/analysis-upload-path';

const ALLOWED_EXTENSIONS = new Set(['csv', 'json', 'xlsx', 'md']);

export {
  isSafeUploadLogicalPath,
  normalizeUploadLogicalPath,
} from '@/lib/analysis-upload-path';

export function normalizeUploadSelection(
  files: Iterable<File>,
  mode: 'files' | 'folder',
): { uploads: AnalysisUpload[]; skippedCount: number } {
  const uploads: AnalysisUpload[] = [];
  let skippedCount = 0;
  for (const file of files) {
    const extension = file.name.split('.').pop()?.toLocaleLowerCase('en-US') ?? '';
    if (!ALLOWED_EXTENSIONS.has(extension)) {
      if (mode === 'folder') {
        skippedCount += 1;
        continue;
      }
      throw new Error('분석 자료는 CSV, JSON, XLSX, MD 파일만 선택할 수 있습니다.');
    }
    const raw = mode === 'folder' ? file.webkitRelativePath : file.name;
    const logicalPath = normalizeUploadLogicalPath(raw, file.name);
    if (logicalPath === null) {
      throw new Error('안전하지 않은 폴더 경로가 포함되어 있습니다.');
    }
    const parts = logicalPath.split('/');
    uploads.push({
      file,
      logicalPath,
      collectionLabel: mode === 'folder' ? parts[0] : '개별 파일',
    });
  }
  return { uploads, skippedCount };
}
