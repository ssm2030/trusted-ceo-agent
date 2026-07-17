import path from "node:path";

import { activateRegisteredReport } from "@/lib/server/registered-report-service";
import { handleRegisteredReportActivation } from "@/lib/server/registered-report-route-handler";
import { getReportRuntime } from "@/lib/server/report-runtime";
import { RunRegistry } from "@/lib/server/run-registry";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function configuredRegistry(): RunRegistry {
  const registryPath = process.env.TRUSTED_CEO_RUN_REGISTRY_PATH;
  const allowlistRoot =
    process.env.TRUSTED_CEO_RUN_ALLOWLIST_ROOT;
  if (
    registryPath === undefined ||
    allowlistRoot === undefined ||
    !path.isAbsolute(registryPath) ||
    !path.isAbsolute(allowlistRoot)
  ) {
    throw new Error("registered report runtime is not configured");
  }
  return new RunRegistry(registryPath, allowlistRoot);
}

export async function POST(request: Request): Promise<Response> {
  const reportRuntime = getReportRuntime();
  return handleRegisteredReportActivation(request, {
    security: reportRuntime.security,
    activate: async (registrationId) =>
      activateRegisteredReport(registrationId, {
        registry: configuredRegistry(),
        store: reportRuntime.store,
      }),
  });
}
