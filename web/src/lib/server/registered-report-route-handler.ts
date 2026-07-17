import type { ViewerEligibilityDecisionV1 } from "../../../../contracts/web-report/v1/generated/types";

import {
  LocalRequestSecurityError,
  type LocalSecurityConfig,
  assertLocalMutation,
} from "@/lib/server/local-request-security";
import { eligibilityFromDecision } from "@/lib/server/report-presentation";

const MAX_REGISTRATION_REQUEST_BYTES = 4 * 1024;
const REGISTRATION_ID_PATTERN =
  /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const RESPONSE_HEADERS = {
  "Cache-Control": "no-store",
  "Content-Security-Policy":
    "default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
  "Content-Type": "application/json; charset=utf-8",
  "X-Content-Type-Options": "nosniff",
} as const;

export type RegisteredReportRouteDependencies = Readonly<{
  security: LocalSecurityConfig;
  activate: (
    registrationId: string,
  ) => Promise<ViewerEligibilityDecisionV1>;
}>;

function response(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: RESPONSE_HEADERS,
  });
}

async function boundedJson(request: Request): Promise<unknown> {
  if (request.headers.get("content-type") !== "application/json") {
    throw new TypeError("invalid content type");
  }
  const length = request.headers.get("content-length");
  if (length === null || !/^[0-9]+$/.test(length)) {
    throw new TypeError("invalid content length");
  }
  const expectedBytes = Number(length);
  if (
    !Number.isSafeInteger(expectedBytes) ||
    expectedBytes <= 0 ||
    expectedBytes > MAX_REGISTRATION_REQUEST_BYTES
  ) {
    throw new TypeError("invalid content length");
  }
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (
    bytes.byteLength !== expectedBytes ||
    bytes.byteLength > MAX_REGISTRATION_REQUEST_BYTES
  ) {
    throw new TypeError("invalid content length");
  }
  return JSON.parse(
    new TextDecoder("utf-8", { fatal: true }).decode(bytes),
  ) as unknown;
}

export async function handleRegisteredReportActivation(
  request: Request,
  dependencies: RegisteredReportRouteDependencies,
): Promise<Response> {
  try {
    assertLocalMutation(request.headers, dependencies.security);
    const document = await boundedJson(request);
    if (
      typeof document !== "object" ||
      document === null ||
      Array.isArray(document) ||
      Object.keys(document).length !== 1 ||
      !("registration_id" in document) ||
      typeof document.registration_id !== "string" ||
      !REGISTRATION_ID_PATTERN.test(document.registration_id)
    ) {
      return response(
        { message: "실행 registration_id가 올바르지 않습니다." },
        400,
      );
    }
    const decision = await dependencies.activate(
      document.registration_id,
    );
    return response(
      {
        activated: true,
        eligibility: eligibilityFromDecision(decision),
      },
      201,
    );
  } catch (error) {
    if (error instanceof LocalRequestSecurityError) {
      return response({ message: error.message }, error.status);
    }
    if (
      error instanceof TypeError ||
      error instanceof SyntaxError ||
      error instanceof URIError
    ) {
      return response(
        { message: "실행 등록 요청이 올바르지 않습니다." },
        400,
      );
    }
    return response(
      { message: "등록된 결과를 검증할 수 없습니다." },
      422,
    );
  }
}
