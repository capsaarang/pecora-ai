"use client";

import { useMemo, useRef, useState } from "react";
import Citation from "./Citation";
import FilingViewer from "./FilingViewer";
import type { CaseFile, Check, Debate } from "@/lib/types";

const VERDICT_TONE: Record<string, string> = {
  UPHELD: "text-upheld", DISMISSED: "text-dismissed", INCONCLUSIVE: "text-inconclusive", ERROR: "text-muted",
};

type Key = string; // `${debate}:${agent}:${index}`
const keyOf = (n: number, agent: string, index: number): Key => `${n}:${agent}:${index}`;

export default function CaseView({ data }: { data: CaseFile }) {
  const { meta, summary, debates } = data;
  const [revealed, setRevealed] = useState(false);
  const [open, setOpen] = useState<number>(0);

  const checks = useMemo(() => {
    const map = new Map<Key, Check>();
    debates.forEach((d, n) => d.citations?.checks?.forEach((c) => map.set(keyOf(n, c.agent, c.index), c)));
    return map;
  }, [debates]);

  // Start on the first debate's deciding quote
  const [selected, setSelected] = useState<Key | null>(() => {
    const k = keyOf(0, "adjudicator", 1);
    return checks.get(k)?.filing_spans?.length ? k : null;
  });
  const current = selected ? checks.get(selected) : undefined;
  const viewer = useRef<HTMLElement>(null);
  const select = (k: Key) => {
    setSelected(k);
    // Below the two-column breakpoint the viewer sits under the trial: bring it into view
    if (window.innerWidth < 1024) viewer.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const caption = current ? `${current.agent} ${current.agent === "adjudicator" ? "deciding quote" : `point ${current.index}`}` : null;

  const v = summary.verdicts;
  const integrity = summary.citation_integrity;

  return (
    <div className="space-y-6">
      <div className="case-head flex flex-wrap items-center justify-between gap-3 py-2">
        <p className="label">
          Case file · {revealed ? `${meta.company_name} (${meta.ticker})` : "Sealed filing"} · FY{meta.fiscal_year ?? "?"}
          {meta.filing_date && ` · filed ${meta.filing_date}`} · {meta.anonymized ? "read blind" : "NOT anonymized"}
        </p>
        <button
          type="button"
          onClick={() => setRevealed((r) => !r)}
          className="rounded border border-ink/30 px-3 py-1 font-sans text-sm hover:bg-card"
        >
          {revealed ? "Hide company" : "Reveal company"}
        </button>
      </div>

      {revealed && meta.anonymization && (
        <p className="rounded-md bg-card px-4 py-3 font-sans text-sm text-muted">
          The agents read this filing with {meta.anonymization.aliases.length} company names,{" "}
          {meta.anonymization.people.length} people and {meta.anonymization.products.length} product names masked.{" "}
          {Object.keys(meta.anonymization.leaks).length
            ? `Still visible: ${Object.entries(meta.anonymization.leaks).map(([t, n]) => `${t} ×${n}`).join(", ")}.`
            : "No masked name was left in the text."}
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 font-sans sm:grid-cols-4">
        <Stat big value={summary.signal_score ?? "n/a"} label="Adversarial signal / 100" />
        <Stat value={`${data.screen.findings} → ${debates.length} → ${v.UPHELD ?? 0}`} label="Flagged → tried → upheld" />
        <Stat value={`${v.DISMISSED ?? 0} · ${v.INCONCLUSIVE ?? 0}${v.ERROR ? ` · ${v.ERROR} err` : ""}`} label="Dismissed · inconclusive" />
        <Stat value={integrity == null ? "n/a" : `${Math.round(integrity * 100)}%`} label="Quotes verified" />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <div className="space-y-3">
          {debates.map((d, n) => (
            <DebateCard
              key={n}
              n={n}
              d={d}
              open={open === n}
              onToggle={() => setOpen(open === n ? -1 : n)}
              checks={checks}
              selected={selected}
              onSelect={select}
            />
          ))}
        </div>
        <aside ref={viewer} className="h-[75vh] scroll-mt-20 rounded-md border border-rule bg-card p-4 lg:sticky lg:top-20 lg:h-[calc(100vh-7rem)]">
          <FilingViewer filing={data.filing} spans={current?.filing_spans ?? null} caption={caption} />
        </aside>
      </div>
    </div>
  );
}

function Stat({ value, label, big }: { value: React.ReactNode; label: string; big?: boolean }) {
  return (
    <div className="rounded-md border border-rule bg-card px-4 py-3">
      <div className={`${big ? "text-4xl" : "text-xl"} font-bold font-serif leading-none`}>{value}</div>
      <div className="label mt-2">{label}</div>
    </div>
  );
}

function DebateCard({ n, d, open, onToggle, checks, selected, onSelect }: {
  n: number;
  d: Debate;
  open: boolean;
  onToggle: () => void;
  checks: Map<Key, Check>;
  selected: Key | null;
  onSelect: (k: Key) => void;
}) {
  const cite = (agent: string, index: number, quote?: string, pid?: string) => {
    const k = keyOf(n, agent, index);
    return <Citation quote={quote} passageId={pid} check={checks.get(k)} selected={selected === k} onSelect={() => onSelect(k)} />;
  };
  const penalty = d.final_confidence !== d.raw_confidence;

  return (
    <article className="rounded-md border border-rule bg-card">
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-start justify-between gap-4 p-4 text-left">
        <div>
          <p className="label">{d.finding.severity} · {d.finding.focus_area?.replace("_", " ")} · {d.finding.section}</p>
          <h3 className="mt-1 text-lg font-semibold leading-snug">{n + 1}. {d.finding.title}</h3>
        </div>
        <div className="shrink-0 text-right">
          <span className={`stamp text-sm ${VERDICT_TONE[d.verdict]}`}>{d.verdict}</span>
          <div className="mt-2 font-sans text-sm text-muted">{d.final_confidence}% confidence</div>
        </div>
      </button>

      {open && (
        <div className="space-y-5 border-t border-rule p-4">
          {d.error ? (
            <p className="font-sans text-sm text-auditor">This finding could not be judged: {d.error}</p>
          ) : (
            <>
              <p className="leading-relaxed text-ink/85">{d.finding.detail}</p>
              <div className="grid gap-5 md:grid-cols-2">
                <section className="border-l-4 border-auditor pl-3">
                  <h4 className="label !text-auditor">Auditor · the case against</h4>
                  <p className="mt-1 leading-relaxed">{d.auditor.argument}</p>
                  {d.auditor.key_points?.map((kp, i) => (
                    <div key={i} className="mt-3">
                      <p className="text-[0.95rem] leading-snug"><b>{i + 1}.</b> {kp.point}</p>
                      {cite("auditor", i + 1, kp.quote, kp.passage_id)}
                    </div>
                  ))}
                </section>
                <section className="border-l-4 border-defender pl-3">
                  <h4 className="label !text-defender">Defender · the company&rsquo;s side</h4>
                  <p className="mt-1 leading-relaxed">{d.defender.argument}</p>
                  {d.defender.rebuttals?.map((rb, i) => (
                    <div key={i} className="mt-3">
                      <p className="text-[0.95rem] leading-snug"><b>re {rb.responds_to}.</b> {rb.point}</p>
                      {cite("defender", i + 1, rb.quote, rb.passage_id)}
                    </div>
                  ))}
                  {d.defender.concessions?.map((c, i) => (
                    <p key={i} className="mt-3 text-[0.95rem] italic leading-snug">Concedes: {c}</p>
                  ))}
                </section>
              </div>
              <section className="rounded bg-paper/70 p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h4 className="label">Adjudication</h4>
                  <span className="font-sans text-sm">
                    <b>{d.final_confidence}%</b>
                    {penalty && <span className="text-auditor"> (was {d.raw_confidence}%, halved: deciding quote failed the check)</span>}
                  </span>
                </div>
                <p className="mt-1 leading-relaxed">{d.adjudication.reasoning}</p>
                {cite("adjudicator", 1, d.adjudication.decisive_quote, d.adjudication.decisive_passage_id)}
                {d.adjudication.what_would_change_my_mind && (
                  <p className="mt-2 font-sans text-sm text-muted">Would change my mind: {d.adjudication.what_would_change_my_mind}</p>
                )}
              </section>
              {d.flags.length > 0 && (
                <ul className="font-sans text-sm text-inconclusive">
                  {d.flags.map((f) => <li key={f}>⚠ {f}</li>)}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </article>
  );
}
