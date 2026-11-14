import { ask, type AskTurn } from "@/lib/ask";
import { findCase } from "@/lib/data";
import { isLocalRequest } from "@/lib/jobs";

export const dynamic = "force-dynamic";

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!isLocalRequest(req)) return Response.json({ error: "Local use only" }, { status: 403 });
  const id = (await params).id;
  if (!findCase(id)) return Response.json({ error: "No such case" }, { status: 404 });

  const body = await req.json().catch(() => ({}));
  const question = String(body.question ?? "").trim();
  if (!question) return Response.json({ error: "Type a question first." }, { status: 400 });
  if (question.length > 500) return Response.json({ error: "Keep the question under 500 characters." }, { status: 400 });

  const history: AskTurn[] = (Array.isArray(body.history) ? body.history : [])
    .filter((m: AskTurn) => (m?.role === "user" || m?.role === "assistant") && typeof m.content === "string")
    .slice(-6)
    .map((m: AskTurn) => ({ role: m.role, content: m.content.slice(0, 2000) }));

  return Response.json(await ask(id, question, history));
}
