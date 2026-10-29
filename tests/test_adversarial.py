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


def test_changed_number_is_altered():
    passage = "Net revenue was $12,746,000 for fiscal 2016, compared to $11,200,000 in fiscal 2015."
    r = verify_quote("Net revenue was $92,746,000 for fiscal 2016, compared to $11,200,000 in fiscal 2015", [passage])
    assert not r["verified"] and r["status"] == "altered"
    assert any("92,746,000" in c and "12,746,000" in c for c in r["changes"])


def test_dropped_negation_is_altered():
    passage = ("We do not believe that the outcome of these matters will have a material adverse "
               "effect on our financial position or results of operations.")
    r = verify_quote("We do believe that the outcome of these matters will have a material adverse "
                     "effect on our financial position or results of operations", [passage])
    assert not r["verified"] and r["status"] == "altered"


def test_flipped_direction_is_altered():
    passage = "Gross margin decreased to 14.1% in fiscal 2016 primarily due to higher component costs."
    r = verify_quote("Gross margin increased to 14.1% in fiscal 2016 primarily due to higher component costs", [passage])
    assert not r["verified"] and r["status"] == "altered"


def test_harmless_fuzzy_difference_still_verified():
    passage = "Revenue is recognized when title and risk of loss pass to the customer, net of returns."
    r = verify_quote("Revenue is recognised when title and risk of loss pass to the customer, net of returns", [passage])
    assert r["verified"] and r["status"] == "near"


def test_quote_from_other_passage_is_wrong_passage():
    other = "Our largest distributor accounted for 24% of total revenue in fiscal 2016."
    r = verify_quote("Our largest distributor accounted for 24% of total revenue", [PASSAGE, other], cited=0)
    assert not r["verified"] and r["status"] == "wrong_passage" and r["passage"] == 1


def test_spans_point_into_original_passage():
    passage = "Intro.  \u201cProducts shipped near\nquarter end\u201d were recorded early."
    r = verify_quote('"Products shipped near quarter end"', [passage])
    s, e = r["spans"][0]
    assert r["status"] == "exact"
    assert passage[s:e].replace("\n", " ") == "Products shipped near quarter end"


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
    assert filing_signal([]) is None
    assert filing_signal([err]) is None  # all errored: no score, not a clean 0


def test_select_candidates_skips_info_and_orders():
    mk = lambda sev: Finding("i", sev, "s", "t", "d", "f", "r", "revenue")
    picked = select_candidates([mk("LOW"), mk("INFO"), mk("HIGH"), mk("MEDIUM")], 3)
    assert [f.severity for f in picked] == ["HIGH", "MEDIUM", "LOW"]


# ---------------- truncation and screener failures ----------------
def _fake_claude(stop_reason, text):
    from types import SimpleNamespace
    from pecora.adversarial.llm import ClaudeLLM
    llm = ClaudeLLM.__new__(ClaudeLLM)  # skip the API-key check
    llm.model, llm.max_tokens, llm.calls = "test", 100, 0
    resp = SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])
    llm.client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: resp))
    return llm


def test_truncated_reply_raises_instead_of_returning_broken_json():
    import pytest
    from pecora.adversarial.llm import TruncatedResponse
    with pytest.raises(TruncatedResponse):
        _fake_claude("max_tokens", '{"argument": "cut off')("system", "user")


def test_complete_reply_returned_and_counted():
    llm = _fake_claude("end_turn", '{"ok": true}')
    assert llm("system", "user") == '{"ok": true}' and llm.calls == 1


def test_truncation_becomes_debate_error_not_crash():
    d = AdversarialReviewer(_fake_claude("max_tokens", "{"), FakeRetriever()).review(FINDING)
    assert d.verdict == "ERROR" and "TruncatedResponse" in d.error


def test_screener_records_failed_area():
    from pecora.screen import Screener

    class Broken:
        model = "test"

        def chat(self, system, messages):
            raise RuntimeError("boom")

    result = Screener(Broken()).run("[COMPANY]", "2016", {"revenue": []})
    assert result.findings == [] and "revenue" in result.failed_areas
