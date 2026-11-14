"""
Ask a follow-up question about a case file.

The answer may use only the evidence passages the trial already retrieved, plus the
trial record itself. Every quote in the answer is checked with the same strict verifier
the trial uses, and located in the filing so the site can highlight it.

    python -m pecora.ask --case MDXG_FY2016_anon < question.json
        question.json: {"question": "...", "history": [{"role": "user", "content": "..."}, ...]}

Prints one JSON reply: {"answer", "citations", "answerable", "error", "source"}.
The sample case answers its suggested questions offline, with no model call.
"""

import argparse
import json
import os
import re
import sys

from .adversarial.bundle import locate
from .adversarial.llm import parse_json_object
from .adversarial.verifier import verify_quote

MAX_PASSAGES = 24
MAX_PASSAGE_CHARS = 1500
_LOCATABLE = {"exact", "near", "altered", "wrong_passage"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")

ASK_SYSTEM = """You answer follow-up questions about an adversarial review of one SEC 10-K filing.

You are given the filing passages the review used (labeled P1, P2, ...) and the trial record:
each finding, the verdict, the confidence, and the judge's reasoning.

Rules you must follow:
1. Use ONLY the passages and the trial record. No outside knowledge.
2. If you think you recognize the company or know what happened to it later, ignore that completely.
3. Every quote must be copied EXACTLY from a passage, under 40 words, no ellipses. Quotes are
   automatically verified against the filing; invented or altered quotes are flagged to the reader.
4. If the passages cannot answer the question, say so plainly and set "answerable" to false.
5. Answer in 2-5 short sentences of plain English for a non-specialist.
6. Respond with ONE valid JSON object and nothing else."""


def collect_passages(case: dict) -> list[dict]:
    """Unique evidence passages across all debates, relabeled P1..Pn, keeping their filing offsets."""
    seen, passages = set(), []
    for d in case.get("debates", []):
        for ev in d.get("evidence", []) or []:
            text = (ev.get("text") or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            passages.append({"id": f"P{len(passages) + 1}", "section": ev.get("section", ""),
                             "text": text[:MAX_PASSAGE_CHARS], "start": ev.get("start"), "end": ev.get("end")})
            if len(passages) >= MAX_PASSAGES:
                return passages
    return passages


def trial_record(case: dict) -> str:
    lines = []
    for i, d in enumerate(case.get("debates", []), 1):
        f, adj = d.get("finding", {}), d.get("adjudication", {}) or {}
        lines.append(f"Finding {i}: {f.get('title', '')} [{f.get('severity', '')}, {f.get('section', '')}]")
        lines.append(f"  Verdict: {d.get('verdict', '')} at {d.get('final_confidence', 0)}% confidence")
        for key, label in (("reasoning", "Judge's reasoning"), ("auditor_best_point", "Strongest case against"),
                           ("defender_best_point", "Strongest defense"),
                           ("what_would_change_my_mind", "What would change the judge's mind")):
            if adj.get(key):
                lines.append(f"  {label}: {adj[key]}")
    return "\n".join(lines)


def build_prompt(question: str, case: dict, passages: list[dict], history: list[dict] | None = None) -> str:
    block = "\n\n".join(f"[{p['id']}] ({p['section']})\n{p['text']}" for p in passages)
    convo = ""
    if history:
        convo = "\n\nEARLIER IN THIS CONVERSATION\n" + "\n".join(
            f"{str(m.get('role', 'user')).upper()}: {m.get('content', '')}" for m in history[-6:])
    return f"""TRIAL RECORD
{trial_record(case)}

FILING PASSAGES
{block}{convo}

QUESTION
{question}

Respond with this JSON:
{{
  "answer": "2-5 plain sentences",
  "citations": [{{"passage_id": "P1", "quote": "exact text from that passage"}}],
  "answerable": true
}}
Give 1-3 citations when the passages support the answer, none when they do not."""


def check_citation(quote: str, passage_id: str, passages: list[dict], filing_text: str = "") -> dict:
    """Verify one answer quote against the passages and locate it in the filing."""
    ids = [p["id"] for p in passages]
    cited = ids.index(passage_id) if passage_id in ids else None
    r = verify_quote(quote, [p["text"] for p in passages], cited=cited)
    p = passages[r["passage"]] if r["passage"] is not None else None
    spans = []
    if p and r["status"] in _LOCATABLE and filing_text and p.get("end") and p["end"] > (p.get("start") or 0):
        spans = [s for a, b in r["spans"] if (s := locate(filing_text, p["start"], p["end"], p["text"][a:b]))]
    return {"passage_id": passage_id, "found_in": p["id"] if p else None, "quote": quote,
            "section": p["section"] if p else "", "status": r["status"], "verified": r["verified"],
            "score": r["score"], "changes": r["changes"], "filing_spans": spans}


def canned_answer(case: dict, question: str) -> dict | None:
    """The sample case's stored answer to one of its suggested questions."""
    key = re.sub(r"[^a-z0-9 ]", "", question.lower()).strip()
    for qa in case.get("demo_qa", []) or []:
        if re.sub(r"[^a-z0-9 ]", "", qa["question"].lower()).strip() == key:
            return {"answer": qa["answer"], "citations": qa["citations"], "answerable": True,
                    "error": "", "source": "sample"}
    return None


def answer_question(question: str, case: dict, llm, history: list[dict] | None = None) -> dict:
    passages = collect_passages(case)
    if not passages:
        return {"answer": "This case has no saved filing passages, so there is nothing to answer from.",
                "citations": [], "answerable": False, "error": "", "source": "none"}
    try:
        data = parse_json_object(llm(ASK_SYSTEM, build_prompt(question, case, passages, history)))
    except Exception as e:  # report it in the reply, keep the conversation going
        return {"answer": "Claude could not be reached. Log in to the Claude CLI, or set PECORA_LLM=api with "
                          "a key in .env, then ask again.",
                "citations": [], "answerable": False, "error": f"{type(e).__name__}: {e}", "source": "error"}

    text = (case.get("filing") or {}).get("text", "")
    citations = [check_citation(str(c.get("quote", "")), str(c.get("passage_id", "")), passages, text)
                 for c in (data.get("citations") or []) if isinstance(c, dict)]
    return {"answer": str(data.get("answer", "")).strip() or "No answer returned.",
            "citations": citations, "answerable": bool(data.get("answerable", True)),
            "error": "", "source": "model"}


def load_case(case_id: str, data_dir: str = os.path.join("web", "data")) -> dict:
    if not _SAFE_ID.match(case_id):
        raise ValueError(f"bad case id {case_id!r}")
    with open(os.path.join(data_dir, "cases", f"{case_id}.json"), encoding="utf-8") as f:
        return json.load(f)


def reply_for(case: dict, question: str, history: list[dict] | None = None, llm=None) -> dict:
    canned = canned_answer(case, question)
    if canned:
        return canned
    if llm is None:
        from .adversarial.llm import make_llm
        llm = make_llm()
    return answer_question(question, case, llm, history)


def main():
    from dotenv import load_dotenv
    load_dotenv()
    p = argparse.ArgumentParser(description="Answer a follow-up question about a Pecora.ai case file")
    p.add_argument("--case", required=True)
    p.add_argument("--data", default=os.path.join("web", "data"))
    args = p.parse_args()
    body = json.loads(sys.stdin.read() or "{}")
    question = str(body.get("question", "")).strip()
    history = [m for m in body.get("history", []) if isinstance(m, dict)][-6:]
    if not question:
        reply = {"answer": "Type a question first.", "citations": [], "answerable": False, "error": "", "source": "none"}
    else:
        reply = reply_for(load_case(args.case, args.data), question, history)
    print(json.dumps(reply))


if __name__ == "__main__":
    main()
