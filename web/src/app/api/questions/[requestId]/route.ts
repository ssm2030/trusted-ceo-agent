import {
  handleQuestionCancel,
  handleQuestionRead,
} from "@/lib/server/questions/question-route-handlers";
import {
  getQuestionServices,
} from "@/lib/server/questions/services";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ requestId: string }>;
};

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const { requestId } = await context.params;
  return handleQuestionRead(
    request,
    requestId,
    getQuestionServices(),
  );
}

export async function DELETE(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const { requestId } = await context.params;
  return handleQuestionCancel(
    request,
    requestId,
    getQuestionServices(),
  );
}
