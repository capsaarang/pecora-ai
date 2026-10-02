"""
Screener: first-pass candidate finding generator (v1 single-pass auditor)

Sends retrieved 10-K context to Anthropic Claude for audit analysis.
Supports an agentic follow-up loop: if the LLM requests additional
context, the retriever fetches it and the LLM gets another pass.
"""

import json
import os
import re
from dataclasses import dataclass, field, asdict

import anthropic

from .retrieval.focus_areas import FOCUS_AREAS


MODEL = os.environ.get("PECORA_MODEL", "claude-sonnet-5")
MAX_TOKENS = 4096
MAX_FOLLOWUP_ROUNDS = 2  # agentic follow-up iterations


@dataclass
class Finding:
    id: str
    severity: str          # HIGH | MEDIUM | LOW | INFO
    section: str           # e.g. "Item 1A — Risk Factors"
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
    risk_score: int
    sections_reviewed: int
    total_chunks_analyzed: int
    summary: str
    findings: list[Finding] = field(default_factory=list)
    audit_date: str = ""
    model_used: str = MODEL
    focus_areas_run: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class Screener:
    """
    Orchestrates LLM-based audit analysis over retrieved 10-K chunks.

    For each focus area:
      1. Builds a detailed prompt with retrieved context
      2. Calls Claude to generate structured findings (JSON)
      3. Optionally runs follow-up retrieval if Claude flags gaps (agentic loop)
      4. Aggregates all findings and computes an overall risk score

    Usage:
        screener = Screener()
        result = screener.run(
            ticker='AAPL',
            fiscal_year='2023',
            retrieved_context={'risk_factors': [...], 'revenue': [...]},
            retriever=retriever,  # for agentic follow-up
        )
    """

    def __init__(self, api_key: str | None = None):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set. Export it or pass api_key=.")
        self.client = anthropic.Anthropic(api_key=key)

    def run(
        self,
        ticker: str,
        fiscal_year: str,
        retrieved_context: dict[str, list[dict]],
        retriever=None,
        total_chunks: int = 0,
    ) -> AuditResult:
        """
        Run the full audit across all focus areas.

        Args:
            ticker: Company ticker (e.g. 'AAPL')
            fiscal_year: Fiscal year string (e.g. '2023')
            retrieved_context: Dict of focus_key → list of retrieval results
            retriever: Retriever instance for agentic follow-up (optional)
            total_chunks: Total chunks indexed (for metadata)

        Returns:
            AuditResult with all findings and risk score
        """
        from datetime import date
        all_findings: list[Finding] = []
        focus_keys = list(retrieved_context.keys())

        for i, key in enumerate(focus_keys):
            area = FOCUS_AREAS[key]
            chunks = retrieved_context[key]
            print(f"\n[Screener] Focus area {i+1}/{len(focus_keys)}: {area['label']} ({len(chunks)} chunks)")

            findings = self._analyze_focus_area(
                ticker=ticker,
                fiscal_year=fiscal_year,
                focus_key=key,
                area=area,
                chunks=chunks,
                retriever=retriever,
            )
            all_findings.extend(findings)
            print(f"  → {len(findings)} findings generated")

        # Overall summary + risk score
        print("\n[Screener] Generating executive summary and risk score...")
        summary, risk_score = self._generate_summary(
            ticker=ticker,
            fiscal_year=fiscal_year,
            findings=all_findings,
            focus_keys=focus_keys,
        )

        return AuditResult(
            ticker=ticker.upper(),
            fiscal_year=fiscal_year,
            risk_score=risk_score,
            sections_reviewed=len(focus_keys),
            total_chunks_analyzed=total_chunks,
            summary=summary,
            findings=all_findings,
            audit_date=str(date.today()),
            model_used=MODEL,
            focus_areas_run=focus_keys,
        )

    def _analyze_focus_area(
        self,
        ticker: str,
        fiscal_year: str,
        focus_key: str,
        area: dict,
        chunks: list[dict],
        retriever=None,
    ) -> list[Finding]:
        """Run LLM analysis for one focus area with optional agentic follow-up."""

        context_str = self._format_context(chunks)
        messages = []

        system_prompt = _build_system_prompt(ticker, fiscal_year)
        user_prompt = _build_focus_prompt(
            ticker=ticker,
            fiscal_year=fiscal_year,
            area=area,
            context=context_str,
        )

        messages.append({"role": "user", "content": user_prompt})

        # First pass
        response_text = self._call_claude(system_prompt, messages)
        messages.append({"role": "assistant", "content": response_text})

        # Agentic follow-up: if LLM requests more context
        if retriever:
            for round_num in range(MAX_FOLLOWUP_ROUNDS):
                followup_query = _extract_followup_request(response_text)
                if not followup_query:
                    break

                print(f"    [Agentic] Follow-up round {round_num+1}: '{followup_query}'")
                extra_chunks = retriever.retrieve_by_query(followup_query, k=4)
                extra_context = self._format_context(extra_chunks)

                followup_msg = (
                    f"Here is additional context you requested:\n\n{extra_context}\n\n"
                    "Please now provide your final structured findings JSON."
                )
                messages.append({"role": "user", "content": followup_msg})
                response_text = self._call_claude(system_prompt, messages)
                messages.append({"role": "assistant", "content": response_text})

        return _parse_findings(response_text, focus_key)

    def _generate_summary(
        self,
        ticker: str,
        fiscal_year: str,
        findings: list[Finding],
        focus_keys: list[str],
    ) -> tuple[str, int]:
        """Generate executive summary and overall risk score from all findings."""

        findings_text = "\n".join([
            f"[{f.severity}] {f.title} ({f.section}): {f.detail[:120]}..."
            for f in findings
        ])

        prompt = f"""You are a senior financial auditor. You have completed an audit of {ticker}'s {fiscal_year} 10-K filing.

Here are all findings across {len(focus_keys)} focus areas:

{findings_text}

Provide:
1. A 3-4 sentence executive summary of the audit. Be specific about the most material risks.
2. An overall risk score from 0-100, where:
   - 0-25: Low risk, clean filing
   - 26-50: Moderate risk, some concerns
   - 51-75: Elevated risk, material issues present
   - 76-100: High risk, significant red flags

Respond in this exact JSON format:
{{
  "summary": "...",
  "risk_score": 62
}}"""

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text

        try:
            clean = re.sub(r"```json|```", "", raw).strip()
            data = json.loads(clean)
            return data.get("summary", "Audit complete."), int(data.get("risk_score", 50))
        except Exception:
            return raw[:500], 50

    def _call_claude(self, system: str, messages: list[dict]) -> str:
        """Make an API call to Claude and return the text response."""
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
        )
        return response.content[0].text

    def _format_context(self, chunks: list[dict]) -> str:
        """Format chunk list into a readable context block."""
        parts = []
        for r in chunks:
            chunk = r["chunk"]
            score = r.get("score", 0)
            parts.append(
                f"[{chunk.item_number} — {chunk.section_name}] (score: {score:.3f})\n{chunk.text.strip()}"
            )
        return "\n\n---\n\n".join(parts) if parts else "No relevant context retrieved."


def _build_system_prompt(ticker: str, fiscal_year: str) -> str:
    return f"""You are an expert AI financial auditor specializing in SEC 10-K filings.

You are auditing {ticker}'s {fiscal_year} annual report. Your job is to:
1. Identify material risks, anomalies, inconsistencies, and red flags
2. Flag language that is vague, misleading, or that understates risk
3. Identify disclosures that warrant further scrutiny
4. Produce structured, actionable findings a human auditor would act on

Be specific. Cite actual text from the filing. Do not hallucinate numbers or quotes not present in the context.
If you need additional context to complete your analysis, say so explicitly with: FOLLOWUP_REQUEST: <your query>"""


def _build_focus_prompt(
    ticker: str,
    fiscal_year: str,
    area: dict,
    context: str,
) -> str:
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

If context is insufficient, include one INFO finding noting the gap, then add: FOLLOWUP_REQUEST: <specific query to retrieve more context>"""


def _parse_findings(response_text: str, focus_key: str) -> list[Finding]:
    """Parse the LLM's JSON array response into Finding objects."""
    # Extract JSON array from response
    match = re.search(r"\[.*\]", response_text, re.DOTALL)
    if not match:
        print(f"    [Screener] Warning: could not parse findings JSON for {focus_key}")
        return []

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        print(f"    [Screener] JSON parse error for {focus_key}: {e}")
        return []

    findings = []
    for i, item in enumerate(data):
        findings.append(Finding(
            id=item.get("id", f"{focus_key.upper()[:3]}-{i+1}"),
            severity=item.get("severity", "INFO").upper(),
            section=item.get("section", "Unknown"),
            title=item.get("title", "Untitled finding"),
            detail=item.get("detail", ""),
            flagged_text=item.get("flagged_text", ""),
            recommendation=item.get("recommendation", ""),
            focus_area=focus_key,
        ))

    return findings


def _extract_followup_request(response_text: str) -> str | None:
    """Check if LLM embedded a follow-up retrieval request."""
    match = re.search(r"FOLLOWUP_REQUEST:\s*(.+)", response_text)
    if match:
        return match.group(1).strip()
    return None
