import Link from "next/link";
import { notFound } from "next/navigation";
import CaseView from "@/components/CaseView";
import { findCase } from "@/lib/data";

export const dynamic = "force-dynamic"; // new runs appear without a rebuild

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const c = findCase((await params).id);
  return { title: c ? `Case file FY${c.meta.fiscal_year} · Pecora.ai` : "Case not found · Pecora.ai" };
}

export default async function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const data = findCase((await params).id);
  if (!data) notFound();
  return (
    <div className="space-y-4">
      <Link href="/cases/" className="font-sans text-sm text-muted hover:text-ink">← All case files</Link>
      {data.meta.sample && (
        <p className="rounded-md border-l-4 border-inconclusive bg-card px-4 py-3 font-sans text-sm">
          <b>Sample trial.</b> The company and this filing are fictional, written to show how Pecora.ai works with no
          model call. The quote checks, highlights and scores are computed by the real pipeline code.
        </p>
      )}
      <CaseView data={data} />
    </div>
  );
}
