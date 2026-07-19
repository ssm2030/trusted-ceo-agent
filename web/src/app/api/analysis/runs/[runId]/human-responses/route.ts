import { handleAnalysisHumanResponse } from "@/lib/server/analysis/route-handlers";
import { getAnalysisServices } from "@/lib/server/analysis/services";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ runId: string }> };
export async function POST(request: Request, context: Context): Promise<Response> {
  return handleAnalysisHumanResponse(request, (await context.params).runId, getAnalysisServices());
}
