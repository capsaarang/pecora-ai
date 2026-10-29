"""
Case bundle: what a viewer needs to replay a run offline with every quote highlighted in the filing.

A saved run gains:
  filing.text      the anonymized filing exactly as the agents' passages were cut from it
  filing.sections  [{name, item_number, start, end}] offsets into filing.text
  filing_spans     on each citation check: [[start, end], ...] into filing.text, one per quote fragment
  bundle           {"citations", "located", "exact_confirmed", "mismatches"} from the self-check
"""

import re

from .verifier import _normalize_with_map, normalize

# Quotes that point at real filing text; a not_found quote's best fuzzy window would mislead
_LOCATABLE = {"exact", "near", "altered", "wrong_passage"}


def locate(text: str, start: int, end: int, snippet: str) -> list[int] | None:
    """[start, end] of `snippet` in text, searched within text[start:end], ignoring whitespace, case and quote style."""
    region, index = _normalize_with_map(text[start:end])
    target, _ = _normalize_with_map(snippet)
    pos = region.find(target) if target else -1
    if pos < 0:
        return None
    return [start + index[pos], start + index[pos + len(target) - 1] + 1]


def attach_filing_spans(debates: list[dict], text: str) -> dict:
    """Adds filing_spans to every citation check in place, then self-checks the exact quotes."""
    stats = {"citations": 0, "located": 0, "exact_confirmed": 0, "mismatches": []}
    for d in debates:
        passages = {p["id"]: p for p in d.get("evidence", [])}
        for c in d.get("citations", {}).get("checks", []):
            c["filing_spans"] = []
            p = passages.get(c.get("found_in"))
            if c.get("status") not in _LOCATABLE or p is None or p.get("end", 0) <= p.get("start", 0):
                continue
            stats["citations"] += 1
            c["filing_spans"] = [span for s, e in c["spans"]
                                 if (span := locate(text, p["start"], p["end"], p["text"][s:e]))]
            if c["filing_spans"] and len(c["filing_spans"]) == len(c["spans"]):
                stats["located"] += 1
            if c["status"] == "exact":
                fragments = [normalize(f) for f in re.split(r"\.\.\.|…", c["quote"]) if len(normalize(f)) >= 8]
                found = [normalize(text[s:e]) for s, e in c["filing_spans"]]
                if found == fragments:
                    stats["exact_confirmed"] += 1
                else:
                    stats["mismatches"].append({"agent": c["agent"], "index": c["index"], "quote": c["quote"][:120]})
    return stats


def filing_record(text: str, sections: list) -> dict:
    return {"text": text, "sections": [{"name": s.name, "item_number": s.item_number,
                                        "start": s.start_char, "end": s.end_char} for s in sections]}
