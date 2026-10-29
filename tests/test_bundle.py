"""Offline tests for the case bundle: section/chunk offsets and quote spans in the filing."""

import json
import re

from pecora.adversarial.bundle import attach_filing_spans, filing_record, locate
from pecora.adversarial.review import AdversarialReviewer
from pecora.ingestion.chunker import chunk_sections
from pecora.ingestion.sections import detect_sections

FILING = (
    "FORM 10-K\n\n"
    "Item 7. Management's Discussion and Analysis\n\n"
    "We recognize revenue when title\nand risk of loss pass to the customer.  In certain cases, "
    "products shipped near quarter end were recorded as revenue before all acceptance criteria had been met.\n\n"
    "Our largest distributor accounted for 24% of total revenue in fiscal 2016, compared to 34% in fiscal 2015.\n\n"
    "Item 8. Financial Statements\n\nNet revenue was $245,015,000 for the year ended December 31, 2016."
)


def ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def test_sections_and_chunks_point_into_the_filing():
    sections = detect_sections(FILING)
    assert all(FILING[s.start_char:s.end_char] == s.text for s in sections)
    for c in chunk_sections(sections, chunk_size=120, overlap=0):
        assert ws(FILING[c.start:c.end]) == ws(c.text)


def test_locate_ignores_whitespace_case_and_quote_style():
    span = locate(FILING, 0, len(FILING), "WE RECOGNIZE REVENUE when title and risk of loss")
    assert ws(FILING[span[0]:span[1]]) == "We recognize revenue when title and risk of loss"
    assert locate(FILING, 0, 50, "Net revenue was") is None  # outside the searched range


class ChunkRetriever:
    def __init__(self, text):
        self.chunks = chunk_sections(detect_sections(text))

    def retrieve_by_query(self, query, k=5):
        return [{"chunk": c, "score": 1.0} for c in self.chunks if c.item_number.startswith("Item 7")][:k]


def fake_llm(system, user):
    if "AUDITOR in" in system:
        return json.dumps({"argument": "a", "key_points": [
            {"point": "early", "passage_id": "E1",
             "quote": "We recognize revenue when title and risk of loss pass to the customer"},
            {"point": "fragments", "passage_id": "E1",
             "quote": "products shipped near quarter end ... before all acceptance criteria had been met"},
            {"point": "altered", "passage_id": "E1",
             "quote": "Our largest distributor accounted for 44% of total revenue in fiscal 2016"}]})
    if "DEFENDER" in system:
        return json.dumps({"argument": "d", "rebuttals": [], "concessions": []})
    return json.dumps({"verdict": "UPHELD", "confidence": 70, "decisive_passage_id": "E1",
                       "decisive_quote": "were recorded as revenue before all acceptance criteria had been met",
                       "reasoning": "r"})


def test_debate_quotes_are_highlighted_in_the_filing():
    finding = {"title": "Early revenue", "severity": "HIGH", "flagged_text": "recorded as revenue"}
    debate = AdversarialReviewer(fake_llm, ChunkRetriever(FILING)).review(finding).to_dict()
    stats = attach_filing_spans([debate], FILING)

    checks = {(c["agent"], c["index"]): c for c in debate["citations"]["checks"]}
    exact = checks[("auditor", 1)]
    assert ws(FILING[slice(*exact["filing_spans"][0])]) == exact["quote"]
    assert len(checks[("auditor", 2)]["filing_spans"]) == 2  # one span per ellipsis fragment
    altered = checks[("auditor", 3)]
    assert altered["status"] == "altered" and "24%" in FILING[slice(*altered["filing_spans"][0])]
    assert stats["citations"] == stats["located"] == 4
    assert stats["exact_confirmed"] == 3 and stats["mismatches"] == []  # 2 auditor + adjudicator


def test_filing_record_lists_sections():
    rec = filing_record(FILING, detect_sections(FILING))
    assert [s["item_number"] for s in rec["sections"]] == ["Item 7", "Item 8"]
    assert all(rec["text"][s["start"]:s["end"]].startswith("Item") for s in rec["sections"])
