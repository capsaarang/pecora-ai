import { isLocalRequest, readJob } from "@/lib/jobs";

export const dynamic = "force-dynamic";

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!isLocalRequest(req)) return Response.json({ error: "Local use only" }, { status: 403 });
  const job = readJob((await params).id);
  return job ? Response.json(job) : Response.json({ error: "No such job" }, { status: 404 });
}
