import { handleOfficialLink } from "@/lib/server/report-route-handlers";
import { getReportRuntime } from "@/lib/server/report-runtime";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ sourceRef: string }> },
): Promise<Response> {
  const { sourceRef } = await context.params;
  return handleOfficialLink(
    request,
    sourceRef,
    getReportRuntime(),
  );
}
