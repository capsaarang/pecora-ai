import "server-only";
import { readFileSync } from "node:fs";
import path from "node:path";
import type { CaseFile, CaseSummary } from "./types";

// Read on each request from web/data, which every finished run (and `npm run data`) refreshes
const DATA = path.join(process.cwd(), "data");

function read<T>(file: string): T | null {
  try {
    return JSON.parse(readFileSync(path.join(DATA, file), "utf-8")) as T;
  } catch {
    return null;
  }
}

export const listCases = (): CaseSummary[] => read<CaseSummary[]>("index.json") ?? [];

export const findCase = (id: string): CaseFile | null =>
  /^[A-Za-z0-9._-]+$/.test(id) ? read<CaseFile>(path.join("cases", `${id}.json`)) : null;
