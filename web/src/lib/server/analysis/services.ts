import {
  AnalysisBackendClient,
  createAnalysisBackendConfig,
} from "@/lib/server/analysis/backend-client";
import type { AnalysisRouteDependencies } from "@/lib/server/analysis/route-handlers";
import { getReportRuntime } from "@/lib/server/report-runtime";
import { activateServiceReport } from "@/lib/server/service-report-activation";

let services: AnalysisRouteDependencies | undefined;

export function getAnalysisServices(): AnalysisRouteDependencies {
  if (services !== undefined) return services;
  const baseUrl = process.env.TRUSTED_CEO_SERVICE_URL ?? "http://127.0.0.1:8765";
  const internalToken = process.env.TRUSTED_CEO_INTERNAL_TOKEN ?? "";
  const timeoutText = process.env.TRUSTED_CEO_SERVICE_TIMEOUT_MS ?? "30000";
  if (!/^[0-9]+$/u.test(timeoutText)) throw new Error("TRUSTED_CEO_SERVICE_TIMEOUT_MS must be an integer");
  const runtime = getReportRuntime();
  const backend = new AnalysisBackendClient(createAnalysisBackendConfig({
    baseUrl,
    internalToken,
    timeoutMs: Number(timeoutText),
  }));
  services = Object.freeze({
    backend,
    security: runtime.security,
    activateReport: (report) => activateServiceReport(report, {
      store: runtime.store,
    }),
  });
  return services;
}
