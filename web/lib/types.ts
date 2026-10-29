export type Verdict = "UPHELD" | "DISMISSED" | "INCONCLUSIVE" | "ERROR";
export type CitationStatus = "exact" | "near" | "altered" | "wrong_passage" | "not_found" | "empty" | "too short";
export type Span = [number, number];

export interface Finding {
  title: string;
  severity: string;
  section: string;
  detail: string;
  flagged_text: string;
  focus_area: string;
}

export interface Passage {
  id: string;
  section: string;
  text: string;
  chunk_id?: string;
  start?: number;
  end?: number;
}

export interface Check {
  agent: "auditor" | "defender" | "adjudicator";
  index: number;
  quote: string;
  cited: string | null;
  found_in: string | null;
  verified: boolean;
  status: CitationStatus;
  score: number;
  changes: string[];
  filing_spans: Span[];
}

export interface KeyPoint {
  point: string;
  passage_id: string;
  quote: string;
}

export interface Rebuttal extends KeyPoint {
  responds_to: number;
}

export interface Debate {
  finding: Finding;
  evidence: Passage[];
  auditor: { argument?: string; key_points?: KeyPoint[]; strength?: string };
  defender: { argument?: string; rebuttals?: Rebuttal[]; concessions?: string[] };
  adjudication: {
    verdict?: string;
    confidence?: number;
    decisive_passage_id?: string;
    decisive_quote?: string;
    reasoning?: string;
    auditor_best_point?: string;
    defender_best_point?: string;
    what_would_change_my_mind?: string;
  };
  citations: { checks?: Check[]; integrity?: number; decisive_status?: CitationStatus };
  verdict: Verdict;
  raw_confidence: number;
  final_confidence: number;
  flags: string[];
  error: string;
}

export interface Section {
  name: string;
  item_number: string;
  start: number;
  end: number;
}

export interface CaseFile {
  id: string;
  meta: {
    ticker: string;
    company_name: string;
    fiscal_year: number | null;
    filing_date?: string;
    report_date?: string;
    url?: string;
    anonymized: boolean;
    model?: string;
    llm_calls?: number;
    anonymization?: { aliases: string[]; people: string[]; products: string[]; leaks: Record<string, number> };
  };
  summary: {
    signal_score: number | null;
    reviewed: number;
    judged?: number;
    errors?: number;
    verdicts: Record<Verdict, number>;
    citation_integrity: number | null;
  };
  bundle: { citations?: number; located?: number; exact_confirmed?: number };
  screen: { findings: number; failed_areas: Record<string, string> };
  debates: Debate[];
  filing: { text: string; sections: Section[] };
}

export interface CaseSummary {
  id: string;
  ticker: string;
  company_name: string;
  fiscal_year: number | null;
  filing_date?: string;
  anonymized: boolean;
  signal_score: number | null;
  verdicts: Record<Verdict, number>;
  debated: number;
  screened: number;
}
