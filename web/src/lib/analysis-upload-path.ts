const URI_OR_DRIVE = /^[A-Za-z][A-Za-z0-9+.-]*:/u;
const CONTROL = /[\u0000-\u001F\u007F]/u;

export function isSafeUploadLogicalPath(value: string): boolean {
  const parts = value.split('/');
  return value.length > 0 && value.length <= 512 && value.normalize('NFC') === value &&
    !value.startsWith('/') && !value.includes('\\') && !URI_OR_DRIVE.test(value) &&
    parts.every((part) =>
      part.length > 0 && part !== '.' && part !== '..' && !CONTROL.test(part));
}

export function normalizeUploadLogicalPath(
  value: string,
  filename: string,
): string | null {
  const logicalPath = value.normalize('NFC');
  if (!isSafeUploadLogicalPath(logicalPath) ||
      logicalPath.split('/').at(-1) !== filename.normalize('NFC')) {
    return null;
  }
  return logicalPath;
}
