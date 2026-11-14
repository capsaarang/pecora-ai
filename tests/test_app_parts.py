"""Offline tests for follow-up questions, demo mode, and the chat app. No API calls."""

import json
import os

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")

from pecora.ask import answer_question, collect_passages
from pecora.demo import (DEMO_ID, find_demo_answer, list_cases, load_case, load_sample,
                         parse_run_command)


# ---------------- sample case ----------------
def test_sample_case_is_labeled_and_consistent():
    case = load_sample()
    assert case["meta"]["sample"] is True
    assert "fictional" in case["meta"]["company_name"].lower()
    assert case["id"] == DEMO_ID
    s = case["summary"]
    assert s["reviewed"] == len(case["debates"]) == 3
    assert sum(v for k, v in s["verdicts"].items() if k != "ERROR") == 3


def test_sample_case_shows_one_caught_quote():
    case = load_sample()
    misses = [c for d in case["debates"] for c in d["citations"]["checks"] if not c["verified"]]
    assert len(misses) == 1 and misses[0]["agent"] == "defender"


def test_demo_answers_match_and_verify():
    case = load_sample()
    reply = find_demo_answer(case, "why was the revenue finding upheld")
    assert reply and reply["citations"] and all(c["verified"] for c in reply["citations"])
    assert find_demo_answer(case, "something else entirely") is None


# ---------------- run command parsing ----------------
def test_parse_run_command():
    assert parse_run_command("SMCI 2016") == ("SMCI", 2016)
    assert parse_run_command("analyze smci FY2016") == ("SMCI", 2016)
    assert parse_run_command("  ntap 2016 ") == ("NTAP", 2016)
    assert parse_run_command("BRK.B 2020") == ("BRK.B", 2020)
    assert parse_run_command("Why was the revenue finding upheld?") is None
    assert parse_run_command("SMCI") is None


# ---------------- saved cases ----------------
def test_list_and_load_saved_cases(tmp_path):
    case = load_sample()
    run = {"meta": {**case["meta"], "ticker": "ABC", "sample": False}, "summary": case["summary"],
           "debates": case["debates"]}
    (tmp_path / "ABC_FY2016_anon.json").write_text(json.dumps(run))
    (tmp_path / "backtest_x.json").write_text(json.dumps({"rows": [{"ticker": "ABC", "fiscal_year": 2016}],
                                                         "signal_gap": 10}))
    (tmp_path / "broken.json").write_text("{not json")
    items = list_cases(str(tmp_path))
    kinds = sorted(i["kind"] for i in items)
    assert kinds == ["backtest", "case"]
    path = next(i["path"] for i in items if i["kind"] == "case")
    assert load_case(path)["meta"]["ticker"] == "ABC"
    assert load_case(str(tmp_path / "missing.json")) is None


# ---------------- follow-up questions ----------------
def test_collect_passages_dedupes():
    case = load_sample()
    ps = collect_passages(case)
    texts = [p["text"] for p in ps]
    assert len(texts) == len(set(texts)) and ps[0]["id"] == "P1"


def _fake(answer_quote):
    def llm(system, user):
        assert "FILING PASSAGES" in user and "TRIAL RECORD" in user
        return json.dumps({"answer": "Because acceptance was still open.", "answerable": True,
                           "citations": [{"passage_id": "P1", "quote": answer_quote}]})
    return llm


def test_answer_verifies_real_quote():
    reply = answer_question("Why?", load_sample(), _fake("a portion remained subject to customer acceptance testing"))
    assert reply["citations"][0]["verified"] is True
    assert reply["citations"][0]["passage"]


def test_answer_flags_invented_quote():
    reply = answer_question("Why?", load_sample(), _fake("the CFO admitted the sales were fake"))
    assert reply["citations"][0]["verified"] is False


def test_answer_survives_model_failure():
    def broken(system, user):
        raise RuntimeError("network down")
    reply = answer_question("Why?", load_sample(), broken)
    assert reply["citations"] == [] and "network down" in reply["error"]


def test_answer_without_passages():
    reply = answer_question("Why?", {"debates": []}, _fake("x"))
    assert reply["answerable"] is False


# ---------------- the app ----------------
def test_app_home_demo_and_followup():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    at.session_state["case_id"] = DEMO_ID
    at.run()
    assert not at.exception
    assert [m.value for m in at.metric][:2] == ["39/100", "3 of 9"]
    at.session_state["pending"] = ("ask", "Why was the revenue finding upheld?")
    at.run()
    assert not at.exception
    assert any("acceptance testing" in md.value for md in at.markdown)


def test_app_home_free_text_gives_guidance():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.chat_input[0].set_value("hello").run()
    assert not at.exception
    assert any("SMCI 2016" in md.value for md in at.markdown)
