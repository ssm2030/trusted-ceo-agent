import {
  handleQuestionSubmit,
} from "@/lib/server/questions/question-route-handlers";
import {
  getQuestionServices,
} from "@/lib/server/questions/services";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  return handleQuestionSubmit(request, getQuestionServices());
}
