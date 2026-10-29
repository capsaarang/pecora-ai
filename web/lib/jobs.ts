import "server-only";
import { spawn, spawnSync } from "node:child_process";
import { closeSync, existsSync, mkdirSync, openSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

// The site runs from web/; the pipeline and its outputs live one level up
export const REPO = path.resolve(process.cwd(), "..");
const JOBS = path.join(REPO, "outputs", "jobs");
const PYTHON = process.env.PECORA_PYTHON ?? path.join(REPO, ".venv", "bin", "python");
const QUEUE_GRACE_MS = 60_000; // a job that has not started its Python process within this is dead

export type JobStatus = "queued" | "running" | "done" | "error";

export interface Job {
  id: string;
  status: JobStatus;
  ticker: string;
  year: number;
  max_findings: number;
  anonymize: boolean;
  started: string;
  finished: string | null;
  case_id: string | null;
  error: string | null;
  pid?: number;
  summary?: { signal_score: number | null; verdicts: Record<string, number> };
  log?: string[];
}

const safeId = (id: string) => /^[A-Za-z0-9._-]+$/.test(id);

function alive(pid?: number): boolean {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function tail(file: string, lines: number): string[] {
  if (!existsSync(file)) return [];
  return readFileSync(file, "utf-8").split("\n").filter(Boolean).slice(-lines);
}

/** A job's status, with its log tail. A job whose process died without finishing is reported as an error. */
export function readJob(id: string, logLines = 400): Job | null {
  if (!safeId(id)) return null;
  const dir = path.join(JOBS, id);
  const file = path.join(dir, "status.json");
  if (!existsSync(file)) return null;
  const job = JSON.parse(readFileSync(file, "utf-8")) as Job;
  const age = Date.now() - new Date(job.started).getTime();
  if ((job.status === "running" && !alive(job.pid)) || (job.status === "queued" && age > QUEUE_GRACE_MS)) {
    const stderr = tail(path.join(dir, "stderr.txt"), 8).join("\n");
    job.status = "error";
    job.error = `The analysis process stopped unexpectedly.${stderr ? `\n${stderr}` : ""}`;
  }
  return { ...job, log: tail(path.join(dir, "log.txt"), logLines) };
}

export function listJobs(limit = 20): Job[] {
  if (!existsSync(JOBS)) return [];
  return readdirSync(JOBS)
    .map((id) => readJob(id, 0))
    .filter((j): j is Job => j !== null)
    .sort((a, b) => b.started.localeCompare(a.started))
    .slice(0, limit);
}

export const activeJob = (): Job | undefined =>
  listJobs(50).find((j) => j.status === "queued" || j.status === "running");

/** Local time as YYYY-MM-DDTHH:MM:SS, the same format the Python job writes. */
function localTimestamp(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 19);
}

/** Starts `python -m pecora.job` in the background. The Python process writes its own status and log. */
export function startJob(input: { ticker: string; year: number; maxFindings: number; anonymize: boolean }): Job {
  const started = localTimestamp();
  const stamp = started.replace(/[-:]/g, "");
  const id = `${input.ticker}-${input.year}-${stamp}`;
  const dir = path.join(JOBS, id);
  mkdirSync(dir, { recursive: true });
  const job: Job = {
    id, status: "queued", ticker: input.ticker, year: input.year, max_findings: input.maxFindings,
    anonymize: input.anonymize, started, finished: null, case_id: null, error: null,
  };
  writeFileSync(path.join(dir, "status.json"), JSON.stringify(job, null, 1));

  const out = openSync(path.join(dir, "stdout.txt"), "a");
  const err = openSync(path.join(dir, "stderr.txt"), "a");
  const args = ["-m", "pecora.job", "--id", id, "--ticker", input.ticker, "--year", String(input.year),
                "--max-findings", String(input.maxFindings), ...(input.anonymize ? [] : ["--no-anonymize"])];
  const child = spawn(/*turbopackIgnore: true*/ PYTHON, args, { cwd: REPO, detached: true, stdio: ["ignore", out, err] });
  child.unref(); // keeps running even if the dev server restarts
  closeSync(out);
  closeSync(err);
  return job;
}

/** What the Run tab needs before it can start a job. */
export async function health() {
  const python = existsSync(/*turbopackIgnore: true*/ PYTHON);
  const claude = spawnSync("claude", ["--version"], { timeout: 10_000, encoding: "utf-8" }).status === 0;
  let online = false;
  try {
    const res = await fetch("https://www.sec.gov/robots.txt", { method: "HEAD", signal: AbortSignal.timeout(4000) });
    online = res.status < 500;
  } catch {
    online = false;
  }
  return { python, claude, online, active: activeJob() ?? null };
}

/** Only this machine may use the API: the server binds to 127.0.0.1, and requests from other sites are refused. */
export function isLocalRequest(req: Request): boolean {
  const local = /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/;
  const host = req.headers.get("host") ?? "";
  const origin = req.headers.get("origin");
  return local.test(host) && (!origin || local.test(new URL(origin).host));
}
