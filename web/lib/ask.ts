import "server-only";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { REPO } from "./jobs";

const VENV_PYTHON = path.join(REPO, ".venv", "bin", "python");
const PYTHON = process.env.PECORA_PYTHON ?? (existsSync(VENV_PYTHON) ? VENV_PYTHON : "python3");
const TIMEOUT_MS = 180_000;

export interface AskCitation {
  passage_id: string;
  found_in: string | null;
  quote: string;
  section: string;
  status: string;
  verified: boolean;
  score: number;
  changes: string[];
  filing_spans: [number, number][];
}

export interface AskReply {
  answer: string;
  citations: AskCitation[];
  answerable: boolean;
  error: string;
  source: "sample" | "model" | "error" | "none";
}

export interface AskTurn {
  role: "user" | "assistant";
  content: string;
}

/** One follow-up question, answered by `python -m pecora.ask` from the case's own evidence. */
export function ask(caseId: string, question: string, history: AskTurn[]): Promise<AskReply> {
  return new Promise((resolve) => {
    const fail = (error: string): AskReply => ({
      answer: "The question could not be answered. Check that the Python environment is set up, then try again.",
      citations: [], answerable: false, error, source: "error",
    });
    const child = spawn(PYTHON, ["-m", "pecora.ask", "--case", caseId], { cwd: REPO, env: process.env });
    let out = "";
    let err = "";
    const timer = setTimeout(() => {
      child.kill();
      resolve(fail("Timed out after 3 minutes."));
    }, TIMEOUT_MS);
    child.stdout.on("data", (b) => (out += b));
    child.stderr.on("data", (b) => (err += b));
    child.on("error", (e) => {
      clearTimeout(timer);
      resolve(fail(`Could not start Python (${PYTHON}): ${e.message}`));
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      const line = out.trim().split("\n").pop() ?? "";
      try {
        resolve(JSON.parse(line) as AskReply);
      } catch {
        resolve(fail(`Python exited with code ${code}. ${err.trim().split("\n").slice(-3).join(" ")}`));
      }
    });
    child.stdin.end(JSON.stringify({ question, history }));
  });
}
