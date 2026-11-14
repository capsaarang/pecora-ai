"""
Build the sample case used by demo mode and the demo video.

The company, filing text, and trial below are FICTIONAL, written to show how
Pecora.ai works. Verification, confidence penalties, and the signal score are
computed by the real pipeline code, not typed in.

    python data/demo/build_sample_case.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pecora.adversarial.review import Debate, summarize  # noqa: E402
from pecora.adversarial.verifier import verify_debate_quotes, verify_quote  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "sample_case.json")
UNVERIFIED_PENALTY = 0.5


def ev(pid, section, text):
    return {"id": pid, "section": section, "text": text}


TRIALS = [
    {
        "finding": {
            "title": "Quarter-end revenue recognized before customer acceptance",
            "severity": "HIGH", "section": "Item 7", "focus_area": "revenue",
            "detail": "A spike in late-quarter shipments was booked as revenue while acceptance testing was still open.",
            "flagged_text": "a portion remained subject to customer acceptance testing",
        },
        "evidence": [
            ev("E1", "Item 7 - Management's Discussion and Analysis",
               "Net sales for the fourth quarter of 2016 increased 31% compared with the third quarter, driven "
               "primarily by shipments of laboratory analyzer systems to two hospital networks in the final ten days "
               "of the quarter. Of these shipments, a portion remained subject to customer acceptance testing at "
               "December 31, 2016."),
            ev("E2", "Item 8 - Note 2, Revenue Recognition",
               "We recognize revenue when persuasive evidence of an arrangement exists, the product has been shipped, "
               "the price is fixed or determinable and collection is reasonably assured. For certain large system "
               "orders, we recognize revenue upon shipment where we believe customer acceptance provisions are "
               "perfunctory."),
            ev("E3", "Item 9A - Controls and Procedures",
               "Management identified a deficiency in the review of cut-off procedures for shipments near the end of "
               "the fiscal year. Management has concluded that this deficiency does not constitute a material "
               "weakness."),
        ],
        "auditor": {
            "argument": "Revenue jumped 31% in one quarter, almost entirely from shipments in the last ten days, and "
                        "some of those shipments were still waiting on acceptance testing at year end. The company's "
                        "own policy lets it book revenue at shipment when it judges acceptance to be a formality. "
                        "Management also found a weakness in exactly the cut-off controls that would catch this.",
            "strength": "strong",
            "key_points": [
                {"point": "The growth is concentrated in the final days of the quarter.", "passage_id": "E1",
                 "quote": "shipments of laboratory analyzer systems to two hospital networks in the final ten days of the quarter"},
                {"point": "Acceptance testing was still open when the books closed.", "passage_id": "E1",
                 "quote": "a portion remained subject to customer acceptance testing"},
                {"point": "The policy relies on management's own judgment that acceptance is a formality.",
                 "passage_id": "E2",
                 "quote": "we recognize revenue upon shipment where we believe customer acceptance provisions are perfunctory"},
                {"point": "The control meant to catch cut-off errors was itself deficient.", "passage_id": "E3",
                 "quote": "a deficiency in the review of cut-off procedures for shipments near the end of the fiscal year"},
            ],
        },
        "defender": {
            "argument": "Hospital equipment sales are lumpy, and large orders often land at quarter end. The policy "
                        "is disclosed and standard for equipment makers, and management concluded the control issue "
                        "was not a material weakness. Still, I cannot explain why systems awaiting acceptance were "
                        "booked as sales.",
            "rebuttals": [
                {"responds_to": 1, "point": "Late-quarter orders are normal for capital equipment.",
                 "passage_id": "E1", "quote": "driven primarily by shipments of laboratory analyzer systems to two hospital networks"},
                {"responds_to": 4, "point": "Management judged the control gap to be minor.", "passage_id": "E3",
                 "quote": "this deficiency does not constitute a material weakness"},
            ],
            "concessions": ["Systems still in acceptance testing were recorded as revenue; the filing gives no reason "
                            "why acceptance was a formality for these customers."],
        },
        "adjudication": {
            "verdict": "UPHELD", "confidence": 78, "decisive_passage_id": "E1",
            "decisive_quote": "a portion remained subject to customer acceptance testing at December 31, 2016",
            "reasoning": "The filing itself says revenue was booked for systems that had not passed acceptance, in the "
                         "same quarter as an unusual sales spike and a known cut-off control deficiency. The defense "
                         "explains why spikes happen, not why open acceptance was treated as complete. An analyst "
                         "would be right to escalate this.",
            "auditor_best_point": "Revenue was recorded while customer acceptance was still pending.",
            "defender_best_point": "Lumpy year-end orders are common for capital equipment makers.",
            "what_would_change_my_mind": "Disclosure that the open acceptance items were later passed without "
                                         "returns or credits in the following quarter.",
        },
    },
    {
        "finding": {
            "title": "Inventory build includes goods the company may have to buy back",
            "severity": "MEDIUM", "section": "Item 8", "focus_area": "revenue",
            "detail": "Inventory grew sharply and includes stock covered by distributor repurchase commitments.",
            "flagged_text": "goods that we have committed to repurchase",
        },
        "evidence": [
            ev("E1", "Item 8 - Note 4, Inventories",
               "Inventories include finished goods held at third-party logistics locations, including goods that we "
               "have committed to repurchase from certain distributors under stock rotation agreements."),
            ev("E2", "Item 7 - Management's Discussion and Analysis",
               "Inventories increased to $96.4 million at December 31, 2016 from $71.2 million at December 31, 2015, "
               "primarily to support anticipated demand for our next generation analyzer platform."),
        ],
        "auditor": {
            "argument": "Inventory rose about 35% in a year, and some of it is stock the company promised to buy back "
                        "from distributors. If those goods were first recorded as sales to distributors, revenue may "
                        "be overstated by goods that never really left.",
            "strength": "moderate",
            "key_points": [
                {"point": "Some inventory is subject to repurchase commitments.", "passage_id": "E1",
                 "quote": "goods that we have committed to repurchase from certain distributors under stock rotation agreements"},
                {"point": "Inventory grew sharply year over year.", "passage_id": "E2",
                 "quote": "Inventories increased to $96.4 million at December 31, 2016 from $71.2 million"},
            ],
        },
        "defender": {
            "argument": "Stock rotation agreements are common with distributors, and the company says the build is "
                        "for a new product launch. Nothing in the passages says these goods were ever booked as sales.",
            "rebuttals": [
                {"responds_to": 2, "point": "The build is tied to a product launch, not to unsold goods.",
                 "passage_id": "E2",
                 "quote": "primarily to support expected demand for our new analyzer platform"},
                {"responds_to": 1, "point": "The repurchase stock is disclosed openly as inventory.",
                 "passage_id": "E1", "quote": "Inventories include finished goods held at third-party logistics locations"},
            ],
            "concessions": [],
        },
        "adjudication": {
            "verdict": "INCONCLUSIVE", "confidence": 50, "decisive_passage_id": "E1",
            "decisive_quote": "goods that we have committed to repurchase from certain distributors",
            "reasoning": "The repurchase commitment is real and worth a question, but the passages never show these "
                         "goods being recorded as sales first. The arguments genuinely cut both ways.",
            "auditor_best_point": "Inventory includes goods the company is obligated to buy back.",
            "defender_best_point": "Nothing shows the repurchase goods were ever booked as revenue.",
            "what_would_change_my_mind": "The dollar value of goods under repurchase commitments and whether any "
                                         "were previously recognized as sales.",
        },
    },
    {
        "finding": {
            "title": "Dependence on a small number of customers",
            "severity": "LOW", "section": "Item 1A", "focus_area": "risk_factors",
            "detail": "Risk factors warn that a few customers drive most sales.",
            "flagged_text": "a limited number of customers",
        },
        "evidence": [
            ev("E1", "Item 1A - Risk Factors",
               "A significant portion of our net sales is derived from a limited number of customers, and the loss of "
               "any of these customers could materially harm our business."),
            ev("E2", "Item 1A - Risk Factors",
               "Our operating results may fluctuate significantly from quarter to quarter due to a variety of factors, "
               "many of which are outside of our control."),
        ],
        "auditor": {
            "argument": "The company depends on a few large customers, which raises the stakes of any one deal and "
                        "the pressure to close it before quarter end.",
            "strength": "weak",
            "key_points": [
                {"point": "Sales are concentrated in a few customers.", "passage_id": "E1",
                 "quote": "derived from a limited number of customers"},
            ],
        },
        "defender": {
            "argument": "This is standard risk-factor language that appears in almost every equipment maker's 10-K. "
                        "It describes a business risk, not an accounting problem.",
            "rebuttals": [
                {"responds_to": 1, "point": "Generic warning language, not evidence of misstatement.",
                 "passage_id": "E2", "quote": "many of which are outside of our control"},
            ],
            "concessions": [],
        },
        "adjudication": {
            "verdict": "DISMISSED", "confidence": 20, "decisive_passage_id": "E1",
            "decisive_quote": "the loss of any of these customers could materially harm our business",
            "reasoning": "This is boilerplate that nearly every company in the industry uses. It names a risk but "
                         "gives no sign that the numbers are wrong.",
            "auditor_best_point": "Customer concentration raises pressure to close deals early.",
            "defender_best_point": "It is generic risk-factor language with no accounting signal.",
            "what_would_change_my_mind": "Evidence that the large customers were also the late-quarter shipments.",
        },
    },
]

DEMO_QA = [
    ("Why was the revenue finding upheld?",
     "Because the filing itself says some systems were still in customer acceptance testing when the year closed, "
     "yet they were counted as sales. That happened in the same quarter as an unusual sales spike and a known "
     "weakness in the year-end cut-off review.",
     [("P1", "a portion remained subject to customer acceptance testing"),
      ("P3", "a deficiency in the review of cut-off procedures for shipments near the end of the fiscal year")]),
    ("What would change the judge's mind on inventory?",
     "The judge wants to know how much inventory is covered by buy-back commitments, and whether any of it was "
     "first recorded as a sale to distributors. The filing shows the commitment exists but never sizes it.",
     [("P4", "goods that we have committed to repurchase from certain distributors")]),
]


def build() -> dict:
    debates = []
    for t in TRIALS:
        d = Debate(finding=t["finding"], evidence=t["evidence"], auditor=t["auditor"],
                   defender=t["defender"], adjudication=t["adjudication"])
        d.verdict = t["adjudication"]["verdict"]
        d.raw_confidence = t["adjudication"]["confidence"]
        d.citations = verify_debate_quotes(d.auditor, d.defender, d.adjudication, [p["text"] for p in d.evidence])
        d.final_confidence = d.raw_confidence
        if not d.citations["decisive_verified"]:
            d.final_confidence = int(d.raw_confidence * UNVERIFIED_PENALTY)
            d.flags.append("decisive citation not found in filing: confidence halved")
        unverified = [c for c in d.citations["checks"] if not c["verified"]]
        if unverified:
            d.flags.append(f"{len(unverified)} quote(s) could not be found in the filing")
        debates.append(d)

    # Passage ids as pecora.ask.collect_passages numbers them
    from pecora.ask import collect_passages
    case = {"debates": [d.to_dict() for d in debates]}
    passages = {p["id"]: p for p in collect_passages(case)}
    qa = []
    for q, a, cites in DEMO_QA:
        cs = []
        for pid, quote in cites:
            p = passages[pid]
            chk = verify_quote(quote, [p["text"]])
            assert chk["verified"], (pid, quote)
            cs.append({"passage_id": pid, "quote": quote, "section": p["section"], "passage": p["text"],
                       "verified": True, "score": chk["score"]})
        qa.append({"question": q, "answer": a, "citations": cs})

    return {
        "meta": {"ticker": "DEMO", "company_name": "Northwind Instruments (fictional)", "fiscal_year": 2016,
                 "anonymized": True, "sample": True, "screened": 9, "model": "sample case, no model call",
                 "filing_date": None, "run_at": "sample"},
        "summary": summarize(debates),
        "debates": [d.to_dict() for d in debates],
        "demo_qa": qa,
    }


if __name__ == "__main__":
    case = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(case, f, indent=2)
    s = case["summary"]
    print(f"Wrote {OUT}: signal {s['signal_score']}, verdicts {s['verdicts']}, "
          f"citations {s['citation_integrity']}")
