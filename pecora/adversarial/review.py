"""
Adversarial Review

For each candidate finding from the v1 screen:
  1. Gather evidence passages from FAISS (the SAME passages go to all agents)
  2. Auditor argues it is a red flag
  3. Defender argues the company's side
  4. Adjudicator rules, scores confidence, and cites the decisive passage
  5. Verifier checks every quote against the filing; unverified decisive
     citations halve the confidence

Filing-level signal = severity-weighted share of claims that survived review.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from .llm import parse_json_object
from .prompts import (ADJUDICATOR_SYSTEM, AUDITOR_SYSTEM, DEFENDER_SYSTEM,
                      adjudicator_user, auditor_user, defender_user)
from .verifier import verify_debate_quotes

SEVERITY_WEIGHTS = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
VERDICTS = {"UPHELD", "DISMISSED", "INCONCLUSIVE"}
UNVERIFIED_PENALTY = 0.5


@dataclass
class Debate:
    finding: dict
    evidence: list[dict]
    auditor: dict = field(default_factory=dict)
    defender: dict = field(default_factory=dict)
    adjudication: dict = field(default_factory=dict)
    citations: dict = field(default_factory=dict)
    verdict: str = "ERROR"
    raw_confidence: int = 0
    final_confidence: int = 0
    flags: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def select_candidates(findings: list, max_findings: int = 5) -> list:
    """Highest severity first; INFO findings are never debated."""
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    eligible = [f for f in findings if getattr(f, "severity", "").upper() in order]
    return sorted(eligible, key=lambda f: order[f.severity.upper()])[:max_findings]


def filing_signal(debates: list[Debate]) -> int:
    """0-100: severity-weighted share of reviewed claims that were UPHELD, scaled by confidence."""
    reviewed = [d for d in debates if d.verdict != "ERROR"]
    total = sum(SEVERITY_WEIGHTS.get(d.finding.get("severity", "").upper(), 1) for d in reviewed)
    if not total:
        return 0
    upheld = sum(SEVERITY_WEIGHTS.get(d.finding.get("severity", "").upper(), 1) * d.final_confidence / 100
                 for d in reviewed if d.verdict == "UPHELD")
    return round(100 * upheld / total)


def summarize(debates: list[Debate]) -> dict:
    counts = {v: 0 for v in [*VERDICTS, "ERROR"]}
    for d in debates:
        counts[d.verdict] = counts.get(d.verdict, 0) + 1
    checks = [c for d in debates for c in d.citations.get("checks", [])]
    return {
        "signal_score": filing_signal(debates),
        "reviewed": len(debates),
        "verdicts": counts,
        "citation_integrity": round(sum(c["verified"] for c in checks) / len(checks), 3) if checks else None,
        "unverified_decisive": sum(1 for d in debates if d.citations and not d.citations.get("decisive_verified")),
    }


class AdversarialReviewer:
    def __init__(self, llm, retriever=None, k_evidence: int = 5, max_passage_chars: int = 1500):
        self.llm = llm
        self.retriever = retriever
        self.k_evidence = k_evidence
        self.max_passage_chars = max_passage_chars

    # -- evidence ----------------------------------------------------------
    def gather_evidence(self, finding: dict) -> list[dict]:
        passages = []
        if self.retriever is not None:
            query = f"{finding.get('title', '')}. {finding.get('flagged_text', '')}"
            seen = set()
            for r in self.retriever.retrieve_by_query(query, k=self.k_evidence):
                chunk = r["chunk"]
                if chunk.chunk_id in seen:
                    continue
                seen.add(chunk.chunk_id)
                passages.append({"section": f"{chunk.item_number} - {chunk.section_name}",
                                 "text": chunk.text.strip()[: self.max_passage_chars]})
        if not passages and finding.get("flagged_text"):
            passages.append({"section": finding.get("section", ""), "text": finding["flagged_text"]})
        for i, p in enumerate(passages):
            p["id"] = f"E{i + 1}"
        return passages

    @staticmethod
    def format_evidence(evidence: list[dict]) -> str:
        return "\n\n".join(f"[{p['id']}] ({p['section']})\n{p['text']}" for p in evidence)

    # -- debate ------------------------------------------------------------
    def review(self, finding: dict) -> Debate:
        evidence = self.gather_evidence(finding)
        debate = Debate(finding=finding, evidence=evidence)
        if not evidence:
            debate.error = "no evidence retrieved"
            return debate

        block = self.format_evidence(evidence)
        try:
            debate.auditor = parse_json_object(self.llm(AUDITOR_SYSTEM, auditor_user(finding, block)))
            debate.defender = parse_json_object(
                self.llm(DEFENDER_SYSTEM, defender_user(finding, block, debate.auditor)))
            debate.adjudication = parse_json_object(
                self.llm(ADJUDICATOR_SYSTEM,
                         adjudicator_user(finding, block, debate.auditor, debate.defender)))
        except Exception as e:  # keep the run alive; record the failure
            debate.error = f"{type(e).__name__}: {e}"
            return debate

        self._score(debate)
        return debate

    def _score(self, debate: Debate) -> None:
        adj = debate.adjudication
        verdict = str(adj.get("verdict", "")).upper().strip()
        if verdict not in VERDICTS:
            debate.flags.append(f"invalid verdict {verdict!r}, treated as INCONCLUSIVE")
            verdict = "INCONCLUSIVE"
        debate.verdict = verdict

        try:
            conf = int(float(adj.get("confidence", 0)))
        except (TypeError, ValueError):
            conf = 0
        debate.raw_confidence = max(0, min(100, conf))

        ids = {p["id"] for p in debate.evidence}
        if adj.get("decisive_passage_id") not in ids:
            debate.flags.append("decisive passage id does not exist")

        debate.citations = verify_debate_quotes(
            debate.auditor, debate.defender, adj, [p["text"] for p in debate.evidence])

        final = debate.raw_confidence
        if not debate.citations["decisive_verified"]:
            final = int(final * UNVERIFIED_PENALTY)
            debate.flags.append("decisive citation not found in filing: confidence halved")
        if debate.citations["integrity"] < 0.5:
            debate.flags.append("fewer than half of all quotes verified")
        debate.final_confidence = final

    def review_all(self, findings: list[dict], workers: int = 3) -> list[Debate]:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            return list(pool.map(self.review, findings))
