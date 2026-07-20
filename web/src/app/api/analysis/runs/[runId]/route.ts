import { handleAnalysisDelete, handleAnalysisStatus } from "@/lib/server/analysis/route-handlers";
import { getAnalysisServices } from "@/lib/server/analysis/services";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ runId: string }> };
export async function GET(request: Request, context: Context): Promise<Response> {
  return handleAnalysisStatus(request, (await context.params).runId, getAnalysisServices());
}
export async function DELETE(request: Request, context: Context): Promise<Response> {
  return handleAnalysisDelete(request, (await context.params).runId, getAnalysisServices());
}
