import { activeJob, isLocalRequest, listJobs, startJob } from "@/lib/jobs";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  if (!isLocalRequest(req)) return Response.json({ error: "Local use only" }, { status: 403 });
  return Response.json(listJobs());
}

export async function POST(req: Request) {
  if (!isLocalRequest(req)) return Response.json({ error: "Local use only" }, { status: 403 });
  const body = await req.json().catch(() => ({}));
  const ticker = String(body.ticker ?? "").trim().toUpperCase();
  const year = Number(body.year);
  const maxFindings = Number(body.maxFindings ?? 5);
  const anonymize = body.anonymize !== false;

  if (!/^[A-Z][A-Z.-]{0,9}$/.test(ticker)) return Response.json({ error: "Enter a stock ticker, like MDXG." }, { status: 400 });
  if (!Number.isInteger(year) || year < 2001 || year > new Date().getFullYear())
    return Response.json({ error: `Fiscal year must be between 2001 and ${new Date().getFullYear()}.` }, { status: 400 });
  if (!Number.isInteger(maxFindings) || maxFindings < 1 || maxFindings > 8)
    return Response.json({ error: "Findings to debate must be between 1 and 8." }, { status: 400 });

  // One filing at a time: every job draws on the same Claude subscription
  const busy = activeJob();
  if (busy) return Response.json({ error: `Already analyzing ${busy.ticker} FY${busy.year}.`, job: busy }, { status: 409 });
  return Response.json(startJob({ ticker, year, maxFindings, anonymize }), { status: 202 });
}
