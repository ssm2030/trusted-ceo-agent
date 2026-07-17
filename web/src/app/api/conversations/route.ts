import {
  handleConversationDelete,
  handleConversationRead,
} from "@/lib/server/questions/question-route-handlers";
import {
  getQuestionServices,
} from "@/lib/server/questions/services";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  return handleConversationRead(
    request,
    getQuestionServices(),
  );
}

export async function DELETE(
  request: Request,
): Promise<Response> {
  return handleConversationDelete(
    request,
    getQuestionServices(),
  );
}
