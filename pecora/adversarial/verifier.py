"""
Citation verifier: the trust layer.

Every quote an agent produces is checked against the evidence passages it
was given. A verdict whose decisive quote cannot be found in the filing is
penalized, so a hallucinated citation can never carry a finding.

Checks, in order:
  1. Locate the quote in the passage it cites (exact, then fuzzy).
  2. A fuzzy match must not change a number, a negation, a direction word
     (increase/decrease) or a modal (may/will). Fuzzy similarity alone
     scores "$92,746,000" vs "$12,746,000" at 0.97.
  3. A quote found only in a different passage than the one cited is
     reported as wrong_passage, not verified.

Statuses: exact | near (verified) and wrong_passage | altered | not_found |
empty | too short (not verified).
"""

import difflib
import re

FUZZY_THRESHOLD = 0.90
ALTERED_FLOOR = 0.75  # below this a fuzzy match is just a different sentence: not_found

_REPLACEMENTS = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "\xa0": " ",
}

_TOKEN_RE = re.compile(r"\d(?:[\d,]*\d)?(?:\.\d+)?|[a-z]+(?:'[a-z]+)?")
NEGATIONS = {"not", "no", "never", "none", "nor", "neither", "without", "cannot"}
DIRECTION = {"increase", "increased", "increases", "increasing", "decrease", "decreased", "decreases",
             "decreasing", "higher", "lower", "more", "less", "greater", "fewer", "gain", "gains",
             "loss", "losses", "above", "below", "rise", "rose", "fall", "fell", "positive",
             "negative", "favorable", "unfavorable", "adverse", "adversely"}
MODALS = {"may", "might", "will", "would", "could", "can", "must", "shall", "should"}

VERIFIED_STATUSES = {"exact", "near"}


def normalize(s: str) -> str:
    for a, b in _REPLACEMENTS.items():
        s = s.replace(a, b)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s.strip(" .,;:\"'")


def _normalize_with_map(s: str) -> tuple[str, list[int]]:
    """Normalize like normalize() (minus edge stripping) and map each output char to its source index."""
    out, idx, prev_space = [], [], True
    for i, ch in enumerate(s):
        ch = _REPLACEMENTS.get(ch, ch)
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                idx.append(i)
                prev_space = True
            continue
        for c in ch.lower():
            out.append(c)
            idx.append(i)
        prev_space = False
    if out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def _is_critical(tok: str) -> bool:
    return (tok[0].isdigit() or tok in NEGATIONS or tok.endswith("n't")
            or tok in DIRECTION or tok in MODALS)


def _critical_changes(quote: str, window: str) -> list[str]:
    """Numbers, negations, direction words and modals the quote changed relative to the filing."""
    q = _TOKEN_RE.findall(quote)
    w = _TOKEN_RE.findall(window)
    key = lambda t: t.replace(",", "")
    ops = difflib.SequenceMatcher(None, [key(t) for t in q], [key(t) for t in w],
                                  autojunk=False).get_opcodes()
    changes = []
    for k, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "equal":
            continue
        if tag == "insert" and k in (0, len(ops) - 1):
            continue  # extra filing words at the window's edges, not a change
        q_crit = [t for t in q[i1:i2] if _is_critical(t)]
        w_crit = [t for t in w[j1:j2] if _is_critical(t)]
        if sorted(map(key, q_crit)) != sorted(map(key, w_crit)):
            changes.append(f"quote says {' '.join(q_crit) or '(nothing)'!r}, "
                           f"filing says {' '.join(w_crit) or '(nothing)'!r}")
    return changes


def _match_fragment(frag: str, passage: str) -> tuple[float, int, int, list[str]]:
    """Best match of one normalized fragment in a normalized passage: (score, start, end, changes)."""
    pos = passage.find(frag)
    if pos != -1:
        return 1.0, pos, pos + len(frag), []

    words = [m.span() for m in re.finditer(r"\S+", passage)]
    n = len(frag.split())
    if not words or not n:
        return 0.0, 0, 0, []
    if len(words) <= n:
        score = difflib.SequenceMatcher(None, frag, passage).ratio()
        return score, 0, len(passage), _critical_changes(frag, passage)

    def score_at(i: int) -> float:
        window = passage[words[i][0]:words[i + n - 1][1]]
        return difflib.SequenceMatcher(None, frag, window).ratio()

    last = len(words) - n
    step = max(1, n // 4)
    best_i = max(range(0, last + 1, step), key=score_at)
    best_i = max(range(max(0, best_i - step), min(last, best_i + step) + 1), key=score_at)
    start, end = words[best_i][0], words[best_i + n - 1][1]
    # Widen by two words each side so a dropped or added word still lines up
    wide = passage[words[max(0, best_i - 2)][0]:words[min(len(words) - 1, best_i + n + 1)][1]]
    return score_at(best_i), start, end, _critical_changes(frag, wide)


def _check_passage(fragments: list[str], passage: tuple[str, list[int]]) -> dict:
    """All fragments against one passage. Spans are offsets into the ORIGINAL passage text."""
    norm, idx = passage
    scores, spans, changes, exact = [], [], [], True
    for frag in fragments:
        score, s, e, ch = _match_fragment(frag, norm)
        scores.append(score)
        changes += ch
        exact &= score == 1.0
        if e > s:
            spans.append([idx[s], idx[e - 1] + 1])
    return {"score": min(scores), "spans": spans, "changes": changes, "exact": exact}


def verify_quote(quote: str, passages: list[str], threshold: float = FUZZY_THRESHOLD,
                 cited: int | None = None) -> dict:
    """
    Check a quote against evidence passages.

    Ellipses split the quote into fragments; every fragment must be found in the
    same passage. `cited` is the index of the passage the agent named; when given,
    the quote must be found there.

    Returns {"verified", "status", "score", "method", "passage", "spans", "changes"}.
    """
    base = {"verified": False, "score": 0.0, "method": "none", "passage": None,
            "spans": [], "changes": []}
    if not quote or not quote.strip():
        return {**base, "status": "empty", "method": "empty"}

    fragments = [normalize(f) for f in re.split(r"\.\.\.|…", quote)]
    fragments = [f for f in fragments if len(f) >= 8]
    if not fragments:
        return {**base, "status": "too short", "method": "too short"}

    results = [_check_passage(fragments, _normalize_with_map(p)) for p in passages]
    if not results:
        return {**base, "status": "not_found"}

    def ok(r: dict) -> bool:
        return r["score"] >= threshold and not r["changes"]

    def report(i: int, status: str) -> dict:
        r = results[i]
        return {"verified": status in VERIFIED_STATUSES, "status": status, "score": round(r["score"], 3),
                "method": "exact" if r["exact"] else "fuzzy", "passage": i,
                "spans": r["spans"], "changes": r["changes"]}

    cited = cited if cited is not None and 0 <= cited < len(results) else None
    candidates = [cited] if cited is not None else range(len(results))
    for i in candidates:
        if ok(results[i]):
            return report(i, "exact" if results[i]["exact"] else "near")
    if cited is not None:
        elsewhere = [i for i in range(len(results)) if i != cited and ok(results[i])]
        if elsewhere:
            return report(elsewhere[0], "wrong_passage")

    best = max(range(len(results)), key=lambda i: results[i]["score"])
    if results[best]["changes"] and results[best]["score"] >= ALTERED_FLOOR:
        return report(best, "altered")
    return report(best, "not_found")


def verify_debate_quotes(auditor: dict, defender: dict, adjudication: dict,
                         evidence: list[dict]) -> dict:
    """
    Verify all quotes from one debate. Returns per-quote results and summary stats.

    `evidence` is the debate's passage list ({"id": "E1", "text": ...}); each quote is
    checked against the passage its passage_id names.
    """
    ids = [p["id"] for p in evidence]
    texts = [p["text"] for p in evidence]

    def check(agent: str, index: int, quote: str, passage_id) -> dict:
        cited = ids.index(passage_id) if passage_id in ids else None
        r = verify_quote(quote, texts, cited=cited)
        found_in = ids[r["passage"]] if r["passage"] is not None else None
        return {"agent": agent, "index": index, "quote": quote, "cited": passage_id,
                "found_in": found_in, **r}

    checks = []
    for i, kp in enumerate(auditor.get("key_points", []) or []):
        checks.append(check("auditor", i + 1, kp.get("quote", ""), kp.get("passage_id")))
    for i, rb in enumerate(defender.get("rebuttals", []) or []):
        checks.append(check("defender", i + 1, rb.get("quote", ""), rb.get("passage_id")))

    decisive = check("adjudicator", 1, adjudication.get("decisive_quote", ""),
                     adjudication.get("decisive_passage_id"))
    checks.append(decisive)

    verified = sum(1 for c in checks if c["verified"])
    return {
        "checks": checks,
        "decisive_verified": decisive["verified"],
        "decisive_status": decisive["status"],
        "verified_count": verified,
        "total_count": len(checks),
        "integrity": round(verified / len(checks), 3) if checks else 0.0,
    }
