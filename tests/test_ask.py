"""Offline tests for follow-up questions and the sample case. No model calls."""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "data", "demo"))

from build_sample_case import CASE_ID, FILING, build, index_row  # noqa: E402
from pecora.ask import answer_question, canned_answer, check_citation, collect_passages, reply_for  # noqa: E402
from pecora.export import export  # noqa: E402


@pytest.fixture(scope="module")
def case():
    return build()


def test_sample_case_scores_come_from_the_pipeline(case):
    s = case["summary"]
    assert s["signal_score"] == 39
    assert s["verdicts"]["UPHELD"] == 1 and s["verdicts"]["INCONCLUSIVE"] == 1 and s["verdicts"]["DISMISSED"] == 1
    assert case["screen"]["findings"] == 9
    assert case["meta"]["sample"] is True and "fictional" in case["meta"]["company_name"]


def test_sample_case_catches_the_altered_number(case):
    checks = case["debates"][1]["citations"]["checks"]
    altered = [c for c in checks if c["status"] == "altered"]
    assert len(altered) == 1
    assert "86.4" in altered[0]["changes"][0] and "96.4" in altered[0]["changes"][0]


def test_every_locatable_sample_quote_highlights_in_the_filing(case):
    assert case["bundle"]["located"] == case["bundle"]["citations"]
    for d in case["debates"]:
        for c in d["citations"]["checks"]:
            if c["status"] == "exact":
                (a, b), = c["filing_spans"]
                assert FILING[a:b].lower() in c["quote"].lower() or c["quote"].lower() in FILING[a:b].lower()


def test_passages_keep_filing_offsets(case):
    for p in collect_passages(case):
        assert FILING[p["start"]:p["end"]] == p["text"]


def test_canned_answer_matches_loosely(case):
    reply = canned_answer(case, "why was the revenue finding upheld")
    assert reply and reply["source"] == "sample"
    assert all(c["verified"] and c["filing_spans"] for c in reply["citations"])
    assert canned_answer(case, "something else entirely") is None


def test_reply_for_uses_canned_answer_without_a_model(case):
    def no_model(system, user):
        raise AssertionError("the sample's suggested questions must not call the model")
    assert reply_for(case, "What would change the judge's mind on inventory?", llm=no_model)["source"] == "sample"


def test_answer_quotes_are_checked_strictly(case):
    passages = collect_passages(case)
    pid = next(p["id"] for p in passages if "96.4" in p["text"])
    good = check_citation("Inventories increased to $96.4 million at December 31, 2016", pid, passages, FILING)
    bad = check_citation("Inventories increased to $69.4 million at December 31, 2016", pid, passages, FILING)
    assert good["verified"] and good["filing_spans"]
    assert not bad["verified"] and bad["status"] == "altered"


def test_answer_question_with_fake_model(case):
    def fake(system, user):
        assert "TRIAL RECORD" in user and "P1" in user
        return json.dumps({"answer": "Acceptance was still open.", "answerable": True,
                           "citations": [{"passage_id": "P1", "quote": "a portion remained subject to customer acceptance testing"},
                                         {"passage_id": "P1", "quote": "all systems passed acceptance testing"}]})
    reply = answer_question("Why?", case, fake)
    assert reply["source"] == "model"
    assert [c["verified"] for c in reply["citations"]] == [True, False]


def test_model_failure_is_reported_not_raised(case):
    def broken(system, user):
        raise RuntimeError("no credit")
    reply = answer_question("Why?", case, broken)
    assert reply["source"] == "error" and "no credit" in reply["error"]


def test_export_keeps_the_sample_case_listed(tmp_path, case):
    out = tmp_path / "data"
    (out / "cases").mkdir(parents=True)
    (out / "index.json").write_text(json.dumps([index_row(case)]))
    index = export(str(tmp_path / "no_runs"), str(out))
    assert [r["id"] for r in index] == [CASE_ID]
