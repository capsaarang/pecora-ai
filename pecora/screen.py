"""
Screener: first-pass candidate findings for one filing.

For each focus area the model reads the retrieved passages and returns 2-4 findings as a
JSON array. It may ask for more context once per round with a FOLLOWUP_REQUEST line; the
retriever searches this filing for it and the model answers again.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date

from .adversarial.llm import UsageLimitReached, make_llm
from .retrieval.focus_areas import FOCUS_AREAS

MAX_FOLLOWUP_ROUNDS = 2


@dataclass
class Finding:
    id: str
    severity: str          # HIGH | MEDIUM | LOW | INFO
    section: str
    title: str
    detail: str
    flagged_text: str
    recommendation: str
    focus_area: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AuditResult:
    ticker: str
    fiscal_year: str
    sections_reviewed: int
    total_chunks_analyzed: int
    findings: list[Finding] = field(default_factory=list)
    audit_date: str = ""
    model_used: str = ""
    focus_areas_run: list[str] = field(default_factory=list)
    failed_areas: dict[str, str] = field(default_factory=dict)  # focus key -> error

    def to_dict(self) -> dict:
        return asdict(self)


class Screener:
    """Runs every focus area; a failed area is recorded in failed_areas, never silently empty."""

    def __init__(self, llm=None, log=print):
        self.llm = llm or make_llm()
        self.log = log

    def run(self, ticker: str, fiscal_year: str, retrieved_context: dict[str, list[dict]],
            retriever=None, total_chunks: int = 0) -> AuditResult:
        findings: list[Finding] = []
        failed: dict[str, str] = {}
        keys = list(retrieved_context)
        for i, key in enumerate(keys, 1):
            area, chunks = FOCUS_AREAS[key], retrieved_context[key]
            self.log(f"\n[Screener] Focus area {i}/{len(keys)}: {area['label']} ({len(chunks)} chunks)")
            try:
                found = self._analyze_focus_area(ticker, fiscal_year, key, area, chunks, retriever)
            except UsageLimitReached:
                raise
            except Exception as e:  # one bad area should not sink the run, but must be visible
                failed[key] = f"{type(e).__name__}: {e}"
                self.log(f"  → FAILED: {failed[key]}")
                continue
            findings.extend(found)
            self.log(f"  → {len(found)} findings generated")

        return AuditResult(ticker=ticker.upper(), fiscal_year=fiscal_year, sections_reviewed=len(keys),
                           total_chunks_analyzed=total_chunks, findings=findings,
                           audit_date=str(date.today()), model_used=getattr(self.llm, "model", "custom"),
                           focus_areas_run=keys, failed_areas=failed)

    def _analyze_focus_area(self, ticker: str, fiscal_year: str, focus_key: str, area: dict,
                            chunks: list[dict], retriever=None) -> list[Finding]:
        system = _build_system_prompt(ticker, fiscal_year)
        messages = [{"role": "user", "content": _build_focus_prompt(ticker, fiscal_year, area,
                                                                      _format_context(chunks))}]
        reply = self.llm.chat(system, messages)

        for round_num in range(1, MAX_FOLLOWUP_ROUNDS + 1 if retriever else 1):
            query = _extract_followup_request(reply)
            if not query:
                break
            self.log(f"    [Agentic] Follow-up round {round_num}: '{query}'")
            extra = _format_context(retriever.retrieve_by_query(query, k=4))
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"Here is additional context you requested:\n\n{extra}\n\n"
                                                     "Please now provide your final structured findings JSON."}]
            reply = self.llm.chat(system, messages)

        return _parse_findings(reply, focus_key)


def _format_context(chunks: list[dict]) -> str:
    parts = [f"[{r['chunk'].item_number} — {r['chunk'].section_name}] (score: {r.get('score', 0):.3f})\n"
             f"{r['chunk'].text.strip()}" for r in chunks]
    return "\n\n---\n\n".join(parts) if parts else "No relevant context retrieved."


def _build_system_prompt(ticker: str, fiscal_year: str) -> str:
    return f"""You are an expert AI financial auditor specializing in SEC 10-K filings.

You are auditing {ticker}'s {fiscal_year} annual report. Your job is to:
1. Identify material risks, anomalies, inconsistencies, and red flags
2. Flag language that is vague, misleading, or that understates risk
3. Identify disclosures that warrant further scrutiny
4. Produce structured, actionable findings a human auditor would act on

Be specific. Cite actual text from the filing. Do not hallucinate numbers or quotes not present in the context.
If you need more context, put this on its own line after the JSON: FOLLOWUP_REQUEST: <your query>
It searches this filing only, so do not ask for other years' filings, proxy statements or outside documents."""


def _build_focus_prompt(ticker: str, fiscal_year: str, area: dict, context: str) -> str:
    return f"""Audit Focus: {area['label']}

Audit Instructions:
{area['audit_instructions']}

Retrieved 10-K Context:
{context}

Analyze the above context for {ticker} ({fiscal_year}) and produce 2-4 findings for this focus area.

Respond ONLY with a valid JSON array (no markdown, no preamble):
[
  {{
    "id": "F1",
    "severity": "HIGH",
    "section": "Item 1A — Risk Factors",
    "title": "Short title max 8 words",
    "detail": "2-3 sentence detailed finding. Be specific and technical.",
    "flagged_text": "Exact quoted text from the filing that triggered this flag (under 40 words)",
    "recommendation": "Specific action a human auditor or investor should take"
  }}
]

Severity guide:
- HIGH: Material risk, potential misrepresentation, or significant anomaly
- MEDIUM: Noteworthy concern requiring monitoring
- LOW: Minor disclosure gap or stylistic risk language
- INFO: Contextual observation with no immediate action required

If context is insufficient, include one INFO finding noting the gap, then add the FOLLOWUP_REQUEST line."""


def _find_json_array(text: str) -> list | None:
    """The first '[' that decodes as a JSON array of objects; prose like '[COMPANY]' around it is skipped."""
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\[", text):
        try:
            data, _ = decoder.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(data, list) and all(isinstance(x, dict) for x in data):
            return data
    return None


def _parse_findings(response_text: str, focus_key: str) -> list[Finding]:
    """Findings from the model's reply. Raises when there is no findings array, so the area is marked failed."""
    data = _find_json_array(response_text)
    if data is None:
        raise ValueError(f"no findings JSON array in the reply: {response_text[:200]!r}")
    return [Finding(id=item.get("id", f"{focus_key.upper()[:3]}-{i}"),
                    severity=item.get("severity", "INFO").upper(),
                    section=item.get("section", "Unknown"),
                    title=item.get("title", "Untitled finding"),
                    detail=item.get("detail", ""),
                    flagged_text=item.get("flagged_text", ""),
                    recommendation=item.get("recommendation", ""),
                    focus_area=focus_key) for i, item in enumerate(data, 1)]


def _extract_followup_request(response_text: str) -> str | None:
    """A FOLLOWUP_REQUEST on its own line. The phrase inside a JSON string value does not count."""
    match = re.search(r"(?m)^\s*FOLLOWUP_REQUEST:\s*(.+?)\s*$", response_text)
    return match.group(1) if match else None
