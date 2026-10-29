"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

interface Health { python: boolean; claude: boolean; online: boolean; active: Job | null }
interface Job {
  id: string;
  status: "queued" | "running" | "done" | "error";
  ticker: string;
  year: number;
  started: string;
  finished: string | null;
  case_id: string | null;
  error: string | null;
  summary?: { signal_score: number | null; verdicts: Record<string, number> };
  log?: string[];
}

const STEPS = ["Fetch the filing", "Hide the company", "Index the text", "Screen for red flags", "Hold the trials"];

function progress(log: string[]) {
  let step = 0;
  let trials = 0;
  let total = 0;
  for (const line of log) {
    const m = line.match(/\[(\d)\/5\]/);
    if (m) step = Math.max(step, Number(m[1]));
    const t = line.match(/on (\d+) findings/);
    if (t) total = Number(t[1]);
    if (line.includes("Trial done:")) trials += 1;
  }
  return { step, trials, total };
}

function elapsed(from: string, to?: string | null) {
  const s = Math.max(0, Math.round(((to ? new Date(to) : new Date()).getTime() - new Date(from).getTime()) / 1000));
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

export default function RunPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [form, setForm] = useState({ ticker: "", year: new Date().getFullYear() - 1, maxFindings: 5, anonymize: true });
  const [formError, setFormError] = useState<string | null>(null);
  const [, tick] = useState(0);
  const logBox = useRef<HTMLPreElement>(null);

  const refresh = useCallback(async () => {
    const [h, j] = await Promise.all([
      fetch("/api/health/").then((r) => r.json()).catch(() => null),
      fetch("/api/runs/").then((r) => r.json()).catch(() => []),
    ]);
    setHealth(h);
    setJobs(Array.isArray(j) ? j : []);
    if (h?.active) setJob((cur) => cur ?? h.active);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Follow the current job until it finishes
  const running = job && (job.status === "queued" || job.status === "running");
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      const next: Job | null = await fetch(`/api/runs/${job.id}/`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
      if (next) setJob(next);
      if (next && (next.status === "done" || next.status === "error")) refresh();
      tick((n) => n + 1);
    }, 2000);
    return () => clearInterval(timer);
  }, [running, job?.id, refresh]);

  useEffect(() => {
    logBox.current?.scrollTo({ top: logBox.current.scrollHeight });
  }, [job?.log?.length]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!/^[A-Za-z][A-Za-z.-]{0,9}$/.test(form.ticker.trim())) {
      setFormError("Enter a stock ticker, like MDXG.");
      return;
    }
    const res = await fetch("/api/runs/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...form, ticker: form.ticker.trim().toUpperCase() }),
    });
    const body = await res.json();
    if (!res.ok) {
      setFormError(body.error ?? "Could not start the analysis.");
      if (body.job) setJob(body.job);
      return;
    }
    setJob(body);
    refresh();
  }

  const ready = health?.online && health.claude && health.python;
  const p = progress(job?.log ?? []);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
      <div className="space-y-4">
        <StatusBanner health={health} />

        <form onSubmit={submit} className="space-y-4 rounded-md border border-rule bg-card p-5" noValidate>
          <h2 className="label">Analyze a new filing</h2>
          <div className="grid grid-cols-2 gap-3 font-sans text-sm">
            <label className="space-y-1">
              <span className="block text-muted">Ticker</span>
              <input
                value={form.ticker}
                onChange={(e) => { setForm({ ...form, ticker: e.target.value }); setFormError(null); }}
                placeholder="MDXG"
                className="w-full rounded border border-rule bg-paper px-3 py-2 font-mono uppercase outline-none focus:border-ink"
              />
            </label>
            <label className="space-y-1">
              <span className="block text-muted">Fiscal year</span>
              <input
                type="number"
                min={2001}
                max={new Date().getFullYear()}
                value={form.year}
                onChange={(e) => setForm({ ...form, year: Number(e.target.value) })}
                className="w-full rounded border border-rule bg-paper px-3 py-2 font-mono outline-none focus:border-ink"
              />
            </label>
            <label className="space-y-1">
              <span className="block text-muted">Findings to put on trial</span>
              <select
                value={form.maxFindings}
                onChange={(e) => setForm({ ...form, maxFindings: Number(e.target.value) })}
                className="w-full rounded border border-rule bg-paper px-3 py-2 outline-none focus:border-ink"
              >
                {[1, 3, 5, 8].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <label className="flex items-end gap-2 pb-2">
              <input
                type="checkbox"
                checked={form.anonymize}
                onChange={(e) => setForm({ ...form, anonymize: e.target.checked })}
                className="accent-ink"
              />
              <span>Read blind (recommended)</span>
            </label>
          </div>
          {formError && <p className="font-sans text-sm text-auditor" role="alert">{formError}</p>}
          <button
            type="submit"
            disabled={!ready || !!running}
            className="w-full rounded bg-ink px-4 py-2.5 font-sans text-sm text-paper transition hover:bg-ink/85 disabled:cursor-not-allowed disabled:bg-ink/30"
          >
            {running ? "Analysis in progress…" : "Run analysis"}
          </button>
          <p className="font-sans text-xs leading-relaxed text-muted">
            Fetches the original 10-K from SEC EDGAR and runs the screener and trials with your local Claude
            (about 20 to 25 calls, roughly 4 minutes). One filing runs at a time.
          </p>
        </form>

        <RecentRuns jobs={jobs.map((j) => (j.id === job?.id ? job : j))} current={job?.id} onPick={setJob} />
      </div>

      <section className="rounded-md border border-rule bg-card p-5" aria-live="polite">
        {!job ? (
          <div className="flex h-full min-h-64 flex-col items-center justify-center text-center">
            <p className="label">No analysis selected</p>
            <p className="mt-2 max-w-sm font-sans text-sm text-muted">
              Start a new filing, or pick a recent run to see its progress and result.
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-xl font-semibold">{job.ticker} · FY{job.year}</h2>
              <span className="font-sans text-sm text-muted">
                {job.status === "done" ? "Finished" : job.status === "error" ? "Stopped" : "Running"} · {elapsed(job.started, job.finished)}
              </span>
            </div>

            <ol className="grid grid-cols-5 gap-2">
              {STEPS.map((label, i) => {
                const n = i + 1;
                const state = job.status === "done" || n < p.step ? "done" : n === p.step ? (job.status === "error" ? "failed" : "now") : "todo";
                return (
                  <li key={label} className="space-y-1.5">
                    <div className={`h-1.5 rounded-full ${
                      state === "done" ? "bg-dismissed" : state === "now" ? "animate-pulse bg-ink" : state === "failed" ? "bg-auditor" : "bg-rule"
                    }`} />
                    <p className={`font-sans text-[0.7rem] leading-tight ${state === "todo" ? "text-muted" : ""}`}>
                      {label}
                      {n === 5 && p.total > 0 && <span className="text-muted"> ({p.trials}/{p.total})</span>}
                    </p>
                  </li>
                );
              })}
            </ol>

            {job.status === "error" && (
              <p className="whitespace-pre-wrap rounded bg-auditor/10 p-3 font-sans text-sm text-auditor" role="alert">{job.error}</p>
            )}

            {job.status === "done" && job.case_id && (
              <div className="flex flex-wrap items-center justify-between gap-4 rounded border border-rule bg-paper p-4">
                <div className="font-sans text-sm">
                  <span className="font-serif text-3xl font-bold">{job.summary?.signal_score ?? "n/a"}</span>
                  <span className="text-muted"> / 100 signal · </span>
                  {job.summary?.verdicts?.UPHELD ?? 0} upheld, {job.summary?.verdicts?.DISMISSED ?? 0} dismissed,{" "}
                  {job.summary?.verdicts?.INCONCLUSIVE ?? 0} inconclusive
                </div>
                <Link href={`/cases/${job.case_id}/`} className="rounded bg-ink px-4 py-2 font-sans text-sm text-paper hover:bg-ink/85">
                  Open case file →
                </Link>
              </div>
            )}

            <div>
              <p className="label mb-1.5">Progress log</p>
              <pre ref={logBox} className="h-80 overflow-y-auto whitespace-pre-wrap rounded bg-ink/[0.04] p-3 font-mono text-[0.72rem] leading-relaxed text-ink/80">
                {(job.log ?? []).join("\n") || "Waiting for the analysis to start…"}
              </pre>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function StatusBanner({ health }: { health: Health | null }) {
  if (!health) return <p className="rounded-md bg-card p-4 font-sans text-sm text-muted">Checking the analysis setup…</p>;
  const problems = [
    !health.online && "You're offline. Saved cases and statistics still work; a new filing needs internet for SEC EDGAR and Claude.",
    !health.claude && "The Claude CLI was not found. Install Claude Code and run `claude` once to log in.",
    !health.python && "The Python environment (.venv) was not found in the project folder.",
  ].filter(Boolean) as string[];
  if (!problems.length) {
    return <p className="rounded-md bg-dismissed/10 p-4 font-sans text-sm text-dismissed">✓ Online and ready: SEC EDGAR is reachable and your local Claude is set up.</p>;
  }
  return (
    <ul className="space-y-1 rounded-md bg-inconclusive/10 p-4 font-sans text-sm text-inconclusive">
      {problems.map((p) => <li key={p}>⚠ {p}</li>)}
    </ul>
  );
}

function RecentRuns({ jobs, current, onPick }: { jobs: Job[]; current?: string; onPick: (j: Job) => void }) {
  if (!jobs.length) return null;
  const tone = { done: "text-dismissed", error: "text-auditor", running: "text-ink", queued: "text-muted" };
  return (
    <div className="rounded-md border border-rule bg-card p-5">
      <h2 className="label mb-2">Recent runs</h2>
      <ul className="divide-y divide-rule/70 font-sans text-sm">
        {jobs.slice(0, 8).map((j) => (
          <li key={j.id}>
            <button
              type="button"
              onClick={() => onPick(j)}
              className={`flex w-full items-center justify-between gap-3 py-2 text-left hover:text-ink ${j.id === current ? "font-semibold" : ""}`}
            >
              <span>{j.ticker} · FY{j.year}</span>
              <span className="text-xs text-muted">{j.started.replace("T", " ").slice(0, 16)}</span>
              <span className={`text-xs ${tone[j.status]}`}>{j.status}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
