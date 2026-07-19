import { handleAnalysisCreate } from "@/lib/server/analysis/route-handlers";
import { getAnalysisServices } from "@/lib/server/analysis/services";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function POST(request: Request): Promise<Response> {
  return handleAnalysisCreate(request, getAnalysisServices());
}
