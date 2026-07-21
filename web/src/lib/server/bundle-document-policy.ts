export const MAX_REPORT_JSON_DEPTH = 64;
export const MAX_REPORT_ARRAY_ITEMS = 5_000;
export const MAX_SOURCE_PREVIEW_JCS_BYTES = 10 * 1024 * 1024;
const ABSOLUTE_PATH_PATTERN =
  /(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|(?:^|[\s"='(),])[\\/]+(?=[^\\/]|$)|file:(?:\/{1,3}|\\\\))/i;
const RFC6901_JSON_POINTER_PATTERN = /^(?:\/(?:[^~/]|~[01])*)*$/;


export class WebReportValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WebReportValidationError";
  }
}

export function assertNoAbsolutePaths(
  value: unknown,
  inheritedJsonPointerLocator = false,
): void {
  if (typeof value === "string") {
    if (ABSOLUTE_PATH_PATTERN.test(value)) {
      throw new WebReportValidationError("absolute path leak");
    }
    return;
  }
  if (value === null || typeof value !== "object") {
    return;
  }
  if (Array.isArray(value)) {
    for (const child of value) {
      assertNoAbsolutePaths(child, inheritedJsonPointerLocator);
    }
    return;
  }

  const record = value as Record<string, unknown>;
  const isJsonPointerLocator =
    inheritedJsonPointerLocator || record.locator_type === "json_pointer";
  for (const [field, child] of Object.entries(record)) {
    if (
      record.locator_type === "json_pointer" &&
      field === "display_locator"
    ) {
      const prefix = "json-pointer:";
      if (
        typeof child !== "string" ||
        !child.startsWith(prefix) ||
        !RFC6901_JSON_POINTER_PATTERN.test(child.slice(prefix.length))
      ) {
        throw new WebReportValidationError("invalid RFC 6901 JSON Pointer display locator");
      }
      continue;
    }
    const isJsonPointerField =
      isJsonPointerLocator &&
      (field === "json_pointer" || field === "pointer");
    if (isJsonPointerField) {
      if (
        typeof child !== "string" ||
        !RFC6901_JSON_POINTER_PATTERN.test(child)
      ) {
        throw new WebReportValidationError("invalid RFC 6901 JSON Pointer");
      }
      continue;
    }
    assertNoAbsolutePaths(
      child,
      record.locator_type === "json_pointer" && field === "locator",
    );
  }
}


export function assertBoundedJson(
  value: unknown,
  depth = 0,
  seen = new Set<unknown>(),
): void {
  if (depth > MAX_REPORT_JSON_DEPTH) {
    throw new WebReportValidationError(
      `JSON depth exceeds ${MAX_REPORT_JSON_DEPTH}`,
    );
  }
  if (value === null || typeof value !== "object") {
    return;
  }
  if (seen.has(value)) {
    throw new WebReportValidationError("circular JSON value is forbidden");
  }
  seen.add(value);
  if (Array.isArray(value)) {
    if (value.length > MAX_REPORT_ARRAY_ITEMS) {
      throw new WebReportValidationError(
        `JSON array exceeds ${MAX_REPORT_ARRAY_ITEMS} items`,
      );
    }
    for (const child of value) {
      assertBoundedJson(child, depth + 1, seen);
    }
  } else {
    for (const child of Object.values(value)) {
      assertBoundedJson(child, depth + 1, seen);
    }
  }
  seen.delete(value);
}
