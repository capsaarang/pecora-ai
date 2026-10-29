"use client";

import Link from "next/link";
import { useState } from "react";
import type { CaseSummary } from "@/lib/types";

export default function CaseList({ cases }: { cases: CaseSummary[] }) {
  const [named, setNamed] = useState(false);
  if (!cases.length) {
    return (
      <p className="rounded border border-dashed border-rule bg-card p-6 font-sans text-sm text-muted">
        No cases exported yet. Run a filing, then <code className="font-mono">npm run data</code> in web/.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <label className="flex w-fit cursor-pointer items-center gap-2 font-sans text-sm text-muted">
        <input type="checkbox" checked={named} onChange={(e) => setNamed(e.target.checked)} className="accent-ink" />
        Show company names (cases are blind by default)
      </label>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {cases.map((c, i) => (
          <li key={c.id}>
            <Link
              href={`/cases/${c.id}/`}
              className="block h-full rounded-md border border-rule bg-card p-4 transition hover:-translate-y-0.5 hover:border-ink/40 hover:shadow-sm"
            >
              <div className="label">
                Case {i + 1} · FY{c.fiscal_year ?? "?"} · filed {c.filing_date ?? "n/a"}
              </div>
              <div className="mt-1 text-lg font-semibold">{named ? `${c.company_name} (${c.ticker})` : "Sealed filing"}</div>
              <div className="mt-3 flex items-end justify-between font-sans text-sm">
                <span>
                  <span className="text-2xl font-bold">{c.signal_score ?? "n/a"}</span>
                  <span className="text-muted"> / 100 signal</span>
                </span>
                <span className="text-muted">
                  {c.screened} flagged → {c.debated} tried → {c.verdicts.UPHELD ?? 0} upheld
                </span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
