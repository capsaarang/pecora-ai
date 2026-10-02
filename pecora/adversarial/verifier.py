"""
Citation verifier: the trust layer.

Every quote an agent produces is checked against the evidence passages it
was given. A verdict whose decisive quote cannot be found in the filing is
penalized, so a hallucinated citation can never carry a finding.
"""

import difflib
import re

FUZZY_THRESHOLD = 0.90

_REPLACEMENTS = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\xa0": " ",
}


def normalize(s: str) -> str:
    for a, b in _REPLACEMENTS.items():
        s = s.replace(a, b)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s.strip(" .,;:\"'")


def _best_fuzzy(q: str, passage: str) -> float:
    qt, pt = q.split(), passage.split()
    n = len(qt)
    if not qt or not pt:
        return 0.0
    if len(pt) <= n:
        return difflib.SequenceMatcher(None, q, passage).ratio()
    best = 0.0
    step = max(1, n // 4)
    for i in range(0, len(pt) - n + 1, step):
        window = " ".join(pt[i:i + n])
        best = max(best, difflib.SequenceMatcher(None, q, window).ratio())
    return best


def verify_quote(quote: str, passages: list[str], threshold: float = FUZZY_THRESHOLD) -> dict:
    """
    Check a quote against evidence passages.

    Ellipses split the quote into fragments; every fragment must be found.
    Returns {"verified": bool, "score": float, "method": str}
    """
    if not quote or not quote.strip():
        return {"verified": False, "score": 0.0, "method": "empty"}

    fragments = [normalize(f) for f in re.split(r"\.\.\.|\u2026", quote)]
    fragments = [f for f in fragments if len(f) >= 8]
    if not fragments:
        return {"verified": False, "score": 0.0, "method": "too short"}

    norm_passages = [normalize(p) for p in passages]
    scores, methods = [], []
    for frag in fragments:
        if any(frag in p for p in norm_passages):
            scores.append(1.0)
            methods.append("exact")
            continue
        best = max((_best_fuzzy(frag, p) for p in norm_passages), default=0.0)
        scores.append(best)
        methods.append("fuzzy")

    score = min(scores)
    method = "exact" if all(m == "exact" for m in methods) else "fuzzy"
    return {"verified": score >= threshold, "score": round(score, 3), "method": method}


def verify_debate_quotes(auditor: dict, defender: dict, adjudication: dict,
                         passages: list[str]) -> dict:
    """Verify all quotes from one debate. Returns per-quote results and summary stats."""
    checks = []

    for i, kp in enumerate(auditor.get("key_points", []) or []):
        checks.append({"agent": "auditor", "index": i + 1, "quote": kp.get("quote", ""),
                       **verify_quote(kp.get("quote", ""), passages)})
    for i, rb in enumerate(defender.get("rebuttals", []) or []):
        checks.append({"agent": "defender", "index": i + 1, "quote": rb.get("quote", ""),
                       **verify_quote(rb.get("quote", ""), passages)})

    decisive = verify_quote(adjudication.get("decisive_quote", ""), passages)
    checks.append({"agent": "adjudicator", "index": 1,
                   "quote": adjudication.get("decisive_quote", ""), **decisive})

    verified = sum(1 for c in checks if c["verified"])
    return {
        "checks": checks,
        "decisive_verified": decisive["verified"],
        "verified_count": verified,
        "total_count": len(checks),
        "integrity": round(verified / len(checks), 3) if checks else 0.0,
    }
