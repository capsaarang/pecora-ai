"""Offline tests for the adversarial review layer (no API calls)."""

import json

from pecora.adversarial.llm import parse_json_object
from pecora.adversarial.review import AdversarialReviewer, Debate, filing_signal, select_candidates
from pecora.adversarial.verifier import verify_quote
from pecora.screen import Finding
from pecora.ingestion.anonymizer import anonymize_text, build_aliases
from pecora.ingestion.chunker import Chunk
from pecora.ingestion.edgar import select_filing

PASSAGE = ("We recognize revenue when title and risk of loss pass to the customer. "
           "In certain cases, products shipped near quarter end were recorded as revenue "
           "before all acceptance criteria had been met.")


# ---------------- verifier ----------------
def test_exact_quote_verified():
    r = verify_quote("products shipped near quarter end were recorded as revenue", [PASSAGE])
    assert r["verified"] and r["method"] == "exact"


def test_smart_quotes_and_whitespace_normalized():
    r = verify_quote("We  recognize revenue when title and risk of loss pass", ["We recognize revenue when title and\nrisk of loss pass"])
    assert r["verified"]


def test_fabricated_quote_rejected():
    r = verify_quote("management intentionally inflated revenue to meet targets", [PASSAGE])
    assert not r["verified"]


def test_ellipsis_fragments_all_required():
    ok = verify_quote("We recognize revenue ... before all acceptance criteria had been met", [PASSAGE])
    bad = verify_quote("We recognize revenue ... after the auditors resigned in protest", [PASSAGE])
    assert ok["verified"] and not bad["verified"]


# ---------------- anonymizer ----------------
def test_aliases_strip_suffix_and_add_known():
    aliases = build_aliases("SUPER MICRO COMPUTER, INC.", "SMCI")
    assert "SUPER MICRO COMPUTER" in aliases and "Supermicro" in aliases and "SMCI" in aliases
    assert aliases == sorted(aliases, key=len, reverse=True)


def test_anonymize_masks_names_not_substrings():
    text = "Super Micro Computer, Inc. (SMCI) sells servers. Supermicro's CEO Charles Liang. SMCIX fund."
    out = anonymize_text(text, build_aliases("Super Micro Computer, Inc.", "SMCI"), ["Charles Liang"])
    assert "Super Micro" not in out and "Supermicro" not in out and "Liang" not in out
    assert "[COMPANY]'s" in out and "[EXECUTIVE]" in out
    assert "SMCIX" in out  # no partial-word masking


def test_mask_years_optional():
    assert "2016" in anonymize_text("fiscal 2016", [], mask_years=False)
    assert "[YEAR]" in anonymize_text("fiscal 2016", [], mask_years=True)


# ---------------- edgar selection ----------------
def test_select_filing_uses_report_date_and_original():
    filings = [
        {"report_date": "2016-06-30", "filing_date": "2016-08-26", "accession": "a", "primary_doc": "x"},
        {"report_date": "2016-12-31", "filing_date": "2017-02-01", "accession": "b", "primary_doc": "y"},
        {"report_date": "2016-06-30", "filing_date": "2019-05-17", "accession": "c", "primary_doc": "z"},
    ]
    assert select_filing(filings, 2016)["accession"] == "a"
    assert select_filing(filings, 2014) is None


# ---------------- json parsing ----------------
def test_parse_json_with_fences_and_preamble():
    assert parse_json_object('Sure!\n```json\n{"verdict": "UPHELD"}\n```')["verdict"] == "UPHELD"


# ---------------- review orchestration ----------------
class FakeRetriever:
    def retrieve_by_query(self, query, k=5):
        c = Chunk(chunk_id="item-7-000", section_name="MD&A", item_number="Item 7",
                  text=PASSAGE, char_start=0, char_end=len(PASSAGE))
        return [{"chunk": c, "score": 0.9}, {"chunk": c, "score": 0.8}]  # duplicate on purpose


def fake_llm(decisive_quote):
    def llm(system, user):
        if "AUDITOR in" in system:
            return json.dumps({"argument": "a", "strength": "strong", "key_points": [
                {"point": "early revenue", "passage_id": "E1",
                 "quote": "products shipped near quarter end were recorded as revenue"}]})
        if "DEFENDER" in system:
            return json.dumps({"argument": "d", "concessions": [], "rebuttals": [
                {"responds_to": 1, "point": "policy disclosed", "passage_id": "E1",
                 "quote": "We recognize revenue when title and risk of loss pass to the customer"}]})
        return json.dumps({"verdict": "UPHELD", "confidence": 80, "decisive_passage_id": "E1",
                           "decisive_quote": decisive_quote, "reasoning": "r",
                           "auditor_best_point": "x", "defender_best_point": "y",
                           "what_would_change_my_mind": "z"})
    return llm


FINDING = {"title": "Quarter-end revenue", "severity": "HIGH", "section": "Item 7",
           "detail": "d", "flagged_text": "recorded as revenue", "focus_area": "revenue"}


def test_debate_with_verified_citation_keeps_confidence():
    d = AdversarialReviewer(fake_llm("before all acceptance criteria had been met"),
                            FakeRetriever()).review(FINDING)
    assert d.verdict == "UPHELD" and d.final_confidence == 80
    assert len(d.evidence) == 1  # deduplicated
    assert d.citations["integrity"] == 1.0 and not d.flags


def test_hallucinated_decisive_citation_is_penalized():
    d = AdversarialReviewer(fake_llm("the CFO admitted the numbers were fabricated"),
                            FakeRetriever()).review(FINDING)
    assert d.raw_confidence == 80 and d.final_confidence == 40
    assert any("confidence halved" in f for f in d.flags)


def test_llm_failure_recorded_not_raised():
    def broken(system, user):
        return "not json at all"
    d = AdversarialReviewer(broken, FakeRetriever()).review(FINDING)
    assert d.verdict == "ERROR" and d.error


def test_signal_score_weighting():
    high = Debate(finding={"severity": "HIGH"}, evidence=[], verdict="UPHELD", final_confidence=80)
    low = Debate(finding={"severity": "LOW"}, evidence=[], verdict="DISMISSED", final_confidence=90)
    err = Debate(finding={"severity": "HIGH"}, evidence=[], verdict="ERROR")
    assert filing_signal([high, low, err]) == round(100 * (3 * 0.8) / 4)
    assert filing_signal([]) == 0


def test_select_candidates_skips_info_and_orders():
    mk = lambda sev: Finding("i", sev, "s", "t", "d", "f", "r", "revenue")
    picked = select_candidates([mk("LOW"), mk("INFO"), mk("HIGH"), mk("MEDIUM")], 3)
    assert [f.severity for f in picked] == ["HIGH", "MEDIUM", "LOW"]
