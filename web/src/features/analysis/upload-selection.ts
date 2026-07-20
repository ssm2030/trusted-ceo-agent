import type { AnalysisUpload } from '@/features/analysis/analysis-model';

const ALLOWED_EXTENSIONS = new Set(['csv', 'json', 'xlsx', 'md']);
const URI_OR_DRIVE = /^[A-Za-z][A-Za-z0-9+.-]*:/u;
const CONTROL = /[\u0000-\u001F\u007F]/u;

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
    const logicalPath = raw.normalize('NFC');
    const parts = logicalPath.split('/');
    const unsafe = !logicalPath || logicalPath.length > 512 || logicalPath.startsWith('/') ||
      logicalPath.includes('\\') || URI_OR_DRIVE.test(logicalPath) ||
      parts.some((part) => !part || part === '.' || part === '..' || CONTROL.test(part)) ||
      parts.at(-1) !== file.name.normalize('NFC');
    if (unsafe) {
      throw new Error('안전하지 않은 폴더 경로가 포함되어 있습니다.');
    }
    uploads.push({
      file,
      logicalPath,
      collectionLabel: mode === 'folder' ? parts[0] : '개별 파일',
    });
  }
  return { uploads, skippedCount };
}
