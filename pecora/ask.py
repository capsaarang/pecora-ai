"""
Ask a follow-up question about a reviewed filing.

The answer may use only the evidence passages the trial already retrieved, plus the
trial record itself. Every quote in the answer is checked against those passages
with the same verifier the trial uses, so a follow-up answer cannot slip in an
invented citation either.

    from pecora.ask import answer_question
    reply = answer_question("Why was the warranty finding dismissed?", case, llm)
"""

import json

from .adversarial.llm import parse_json_object
from .adversarial.verifier import verify_quote

MAX_PASSAGES = 24
MAX_PASSAGE_CHARS = 1500

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
    """Unique evidence passages across all debates, relabeled P1..Pn."""
    seen, passages = set(), []
    for d in case.get("debates", []):
        for ev in d.get("evidence", []) or []:
            text = (ev.get("text") or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            passages.append({"id": f"P{len(passages) + 1}", "section": ev.get("section", ""),
                             "text": text[:MAX_PASSAGE_CHARS]})
            if len(passages) >= MAX_PASSAGES:
                return passages
    return passages


def trial_record(case: dict) -> str:
    lines = []
    for i, d in enumerate(case.get("debates", []), 1):
        f, adj = d.get("finding", {}), d.get("adjudication", {})
        lines.append(f"Finding {i}: {f.get('title', '')} [{f.get('severity', '')}, {f.get('section', '')}]")
        lines.append(f"  Verdict: {d.get('verdict', '')} at {d.get('final_confidence', 0)}% confidence")
        if adj.get("reasoning"):
            lines.append(f"  Judge's reasoning: {adj['reasoning']}")
        if adj.get("auditor_best_point"):
            lines.append(f"  Strongest case against: {adj['auditor_best_point']}")
        if adj.get("defender_best_point"):
            lines.append(f"  Strongest defense: {adj['defender_best_point']}")
    return "\n".join(lines)


def build_prompt(question: str, case: dict, passages: list[dict], history: list[dict] | None = None) -> str:
    block = "\n\n".join(f"[{p['id']}] ({p['section']})\n{p['text']}" for p in passages)
    convo = ""
    if history:
        recent = history[-6:]
        convo = "\n\nEARLIER IN THIS CONVERSATION\n" + "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in recent)
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


def answer_question(question: str, case: dict, llm, history: list[dict] | None = None) -> dict:
    """
    Returns {"answer", "citations": [{passage_id, quote, section, passage, verified, score}],
             "answerable", "error"}
    """
    passages = collect_passages(case)
    if not passages:
        return {"answer": "This case has no saved filing passages, so I can't answer questions about it.",
                "citations": [], "answerable": False, "error": ""}

    try:
        raw = llm(ASK_SYSTEM, build_prompt(question, case, passages, history))
        data = parse_json_object(raw)
    except Exception as e:  # keep the chat alive
        return {"answer": "I couldn't get an answer from the model. Check your API key and credit, then try again.",
                "citations": [], "answerable": False, "error": f"{type(e).__name__}: {e}"}

    by_id = {p["id"]: p for p in passages}
    citations = []
    for c in data.get("citations", []) or []:
        pid, quote = str(c.get("passage_id", "")), str(c.get("quote", ""))
        p = by_id.get(pid)
        check = verify_quote(quote, [p["text"]] if p else [x["text"] for x in passages])
        citations.append({"passage_id": pid, "quote": quote,
                          "section": p["section"] if p else "",
                          "passage": p["text"] if p else "",
                          "verified": check["verified"], "score": check["score"]})

    return {"answer": str(data.get("answer", "")).strip() or "No answer returned.",
            "citations": citations,
            "answerable": bool(data.get("answerable", True)),
            "error": ""}


def to_json(reply: dict) -> str:
    return json.dumps(reply, indent=2)
