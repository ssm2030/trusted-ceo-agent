import { handleReportImport } from "@/lib/server/report-route-handlers";
import { getReportRuntime } from "@/lib/server/report-runtime";
import { clearCurrentQuestionRunContext } from "@/lib/server/questions/run-context";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  const response = await handleReportImport(request, getReportRuntime());
  if (response.status === 201) {
    clearCurrentQuestionRunContext();
  }
  return response;
}
