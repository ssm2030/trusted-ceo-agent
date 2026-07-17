import { handleSessionBootstrap } from "@/lib/server/report-route-handlers";
import { getReportRuntime } from "@/lib/server/report-runtime";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  return handleSessionBootstrap(request, getReportRuntime());
}
