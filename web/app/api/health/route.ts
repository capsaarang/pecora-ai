import { health, isLocalRequest } from "@/lib/jobs";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  if (!isLocalRequest(req)) return Response.json({ error: "Local use only" }, { status: 403 });
  return Response.json(await health());
}
