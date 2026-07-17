import { tmpdir } from "node:os";
import path from "node:path";

import {
  createLocalSecurityConfig,
  type LocalSecurityConfig,
} from "@/lib/server/local-request-security";
import { ReportStore } from "@/lib/server/report-store";

export type ReportRuntime = Readonly<{
  security: LocalSecurityConfig;
  store: ReportStore;
}>;

export function createReportRuntime(input: {
  port: number;
  runtimeRoot: string;
  sessionSecret?: Uint8Array;
}): ReportRuntime {
  if (!path.isAbsolute(input.runtimeRoot)) {
    throw new Error("report runtime root must be absolute");
  }
  return Object.freeze({
    security: createLocalSecurityConfig({
      port: input.port,
      sessionSecret: input.sessionSecret,
    }),
    store: new ReportStore(input.runtimeRoot),
  });
}

function configuredPort(): number {
  const value = process.env.TRUSTED_CEO_WEB_PORT ?? "3000";
  if (!/^[0-9]+$/.test(value)) {
    throw new Error("TRUSTED_CEO_WEB_PORT must be an integer");
  }
  return Number(value);
}

let runtime: ReportRuntime | undefined;

export function getReportRuntime(): ReportRuntime {
  runtime ??= createReportRuntime({
    port: configuredPort(),
    runtimeRoot:
      process.env.TRUSTED_CEO_WEB_RUNTIME_ROOT ??
      path.join(tmpdir(), "trusted-ceo-agent-web-runtime"),
  });
  return runtime;
}
