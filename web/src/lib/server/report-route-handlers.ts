import type { ViewerEligibilityDecisionV1 } from "../../../../contracts/web-report/v1/generated/types";

import {
  WebReportValidationError,
  validateBundleBytes,
  validateEligibilityDecision,
} from "@/lib/server/bundle-validator";
import {
  ReportImportPolicyError,
  readRequestBodyWithinLimit,
  reportImportMetadataFromHeaders,
} from "@/lib/server/import-policy";
import {
  LocalRequestSecurityError,
  type LocalSecurityConfig,
  assertExactLocalRequest,
  assertLocalMutation,
  assertLocalSession,
  issueLocalSession,
  serializeSessionCookie,
} from "@/lib/server/local-request-security";
import { resolveOfficialUrl as resolveOfficialUrlDefault } from "@/lib/server/official-link-resolver";
import {
  OfficialUrlPolicyError,
  assertOfficialUrl,
} from "@/lib/server/official-url-policy";
import {
  buildClientReportPayload,
  eligibilityFromDecision,
  makeUnverifiedImportDecision,
} from "@/lib/server/report-presentation";
import {
  SourcePreviewError,
  SourcePreviewRepository,
} from "@/lib/server/source-preview-repository";
import type { ReportStore } from "@/lib/server/report-store";

const SAFE_JSON_HEADERS = {
  "Cache-Control": "no-store",
  "Content-Security-Policy":
    "default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
  "Content-Type": "application/json; charset=utf-8",
  "X-Content-Type-Options": "nosniff",
} as const;
const SOURCE_REF_PATTERN =
  /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

export type SessionRouteDependencies = Readonly<{
  security: LocalSecurityConfig;
}>;

export type ReportRouteDependencies = SessionRouteDependencies &
  Readonly<{
    store: ReportStore;
  }>;

export type OfficialLinkRouteDependencies = ReportRouteDependencies &
  Readonly<{
    resolveOfficialUrl?: (
      initialUrl: string,
      policy: Parameters<typeof resolveOfficialUrlDefault>[1],
    ) => Promise<string>;
  }>;

function jsonResponse(
  body: unknown,
  status: number,
  extraHeaders?: HeadersInit,
): Response {
  const headers = new Headers(SAFE_JSON_HEADERS);
  if (extraHeaders !== undefined) {
    const additions = new Headers(extraHeaders);
    additions.forEach((value, key) => headers.set(key, value));
  }
  return new Response(JSON.stringify(body), { status, headers });
}

function safeErrorResponse(error: unknown): Response {
  if (error instanceof LocalRequestSecurityError) {
    return jsonResponse({ message: error.message }, error.status);
  }
  if (error instanceof ReportImportPolicyError) {
    return jsonResponse({ message: error.message }, error.status);
  }
  if (error instanceof SourcePreviewError) {
    const status =
      error.reason === "not_found"
        ? 404
        : error.reason === "invalid_ref"
          ? 400
          : 422;
    return jsonResponse({ message: error.message }, status);
  }
  if (
    error instanceof WebReportValidationError ||
    error instanceof SyntaxError
  ) {
    return jsonResponse(
      { message: "웹 리포트 묶음을 검증할 수 없습니다." },
      422,
    );
  }
  if (error instanceof OfficialUrlPolicyError) {
    return jsonResponse({ message: error.message }, 403);
  }
  return jsonResponse(
    { message: "요청을 처리할 수 없습니다." },
    500,
  );
}

async function validatedCurrent(
  store: ReportStore,
): Promise<{
  bundle: Awaited<ReturnType<typeof validateBundleBytes>>;
  decision: ViewerEligibilityDecisionV1;
} | null> {
  const pair = await store.readCurrentPair();
  if (pair === null) {
    return null;
  }
  const [bundle, decision] = await Promise.all([
    validateBundleBytes(pair.bytes),
    validateEligibilityDecision(pair.decision),
  ]);
  buildClientReportPayload(bundle, decision);
  return { bundle, decision };
}

export async function handleSessionBootstrap(
  request: Request,
  dependencies: SessionRouteDependencies,
): Promise<Response> {
  try {
    assertExactLocalRequest(request.headers, dependencies.security, {
      requireOrigin: true,
    });
    const session = issueLocalSession(dependencies.security);
    return jsonResponse(
      { csrfToken: session.csrfToken },
      200,
      { "Set-Cookie": serializeSessionCookie(session.cookieValue) },
    );
  } catch (error) {
    return safeErrorResponse(error);
  }
}

export async function handleReportImport(
  request: Request,
  dependencies: ReportRouteDependencies,
): Promise<Response> {
  try {
    // The request boundary is intentionally checked before metadata or body.
    assertLocalMutation(request.headers, dependencies.security);
    const metadata = reportImportMetadataFromHeaders(request.headers);
    const bytes = await readRequestBodyWithinLimit(request.body);
    if (bytes.byteLength !== metadata.contentLength) {
      throw new ReportImportPolicyError(
        "결과 리포트의 크기가 요청 정보와 일치하지 않습니다.",
        400,
      );
    }
    const bundle = await validateBundleBytes(bytes);
    const decision = makeUnverifiedImportDecision(bundle);
    await validateEligibilityDecision(decision);
    await dependencies.store.publishVerified(bytes, decision);
    return jsonResponse(
      {
        imported: true,
        eligibility: eligibilityFromDecision(decision),
      },
      201,
    );
  } catch (error) {
    return safeErrorResponse(error);
  }
}

export async function handleCurrentReport(
  request: Request,
  dependencies: ReportRouteDependencies,
): Promise<Response> {
  try {
    assertLocalSession(request.headers, dependencies.security);
    const current = await validatedCurrent(dependencies.store);
    if (current === null) {
      return jsonResponse(
        { message: "웹 리포트 묶음이 아직 준비되지 않았습니다." },
        503,
      );
    }
    return jsonResponse(
      buildClientReportPayload(current.bundle, current.decision),
      200,
    );
  } catch (error) {
    return safeErrorResponse(error);
  }
}

export async function handleSourcePreview(
  request: Request,
  previewRef: string,
  dependencies: ReportRouteDependencies,
): Promise<Response> {
  try {
    assertLocalSession(request.headers, dependencies.security);
    const current = await validatedCurrent(dependencies.store);
    if (current === null) {
      return jsonResponse(
        { message: "웹 리포트 묶음이 아직 준비되지 않았습니다." },
        503,
      );
    }
    const preview = new SourcePreviewRepository(
      current.bundle,
    ).get(previewRef);
    return jsonResponse(preview, 200);
  } catch (error) {
    return safeErrorResponse(error);
  }
}

export async function handleOfficialLink(
  request: Request,
  sourceRef: string,
  dependencies: OfficialLinkRouteDependencies,
): Promise<Response> {
  try {
    assertLocalSession(request.headers, dependencies.security);
    if (!SOURCE_REF_PATTERN.test(sourceRef)) {
      return jsonResponse(
        { message: "잘못된 출처 참조입니다." },
        400,
      );
    }
    const current = await validatedCurrent(dependencies.store);
    if (current === null) {
      return jsonResponse(
        { message: "웹 리포트 묶음이 아직 준비되지 않았습니다." },
        503,
      );
    }
    const source = current.bundle.source_view.find(
      (item) => item.source_ref === sourceRef,
    );
    if (source === undefined || source.official_url === null) {
      return jsonResponse(
        { message: "공식 자료 링크를 찾을 수 없습니다." },
        404,
      );
    }
    const resolver =
      dependencies.resolveOfficialUrl ?? resolveOfficialUrlDefault;
    const finalUrl = await resolver(
      source.official_url,
      current.bundle.official_url_policy,
    );
    assertOfficialUrl(
      source.official_url,
      finalUrl,
      current.bundle.official_url_policy,
    );
    return new Response(null, {
      status: 302,
      headers: {
        "Cache-Control": "no-store",
        "Content-Security-Policy":
          "default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        Location: finalUrl,
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch (error) {
    return safeErrorResponse(error);
  }
}
