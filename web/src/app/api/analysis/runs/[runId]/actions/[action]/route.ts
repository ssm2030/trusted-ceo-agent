import { handleAnalysisAction } from "@/lib/server/analysis/route-handlers";
import { getAnalysisServices } from "@/lib/server/analysis/services";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ runId: string; action: string }> };
export async function POST(request: Request, context: Context): Promise<Response> {
  const params = await context.params;
  return handleAnalysisAction(request, params.runId, params.action, getAnalysisServices());
}
