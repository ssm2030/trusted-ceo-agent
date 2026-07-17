import { handleSourcePreview } from "@/lib/server/report-route-handlers";
import { getReportRuntime } from "@/lib/server/report-runtime";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ previewRef: string }> },
): Promise<Response> {
  const { previewRef } = await context.params;
  return handleSourcePreview(
    request,
    previewRef,
    getReportRuntime(),
  );
}
