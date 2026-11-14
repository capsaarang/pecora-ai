"""
Build the sample case file the website opens as its offline demo trial.

The company, filing text, and trial below are FICTIONAL, written to show how
Pecora.ai works without a model call. Verification, confidence penalties,
filing highlights and the signal score are computed by the real pipeline code,
not typed in.

    python data/demo/build_sample_case.py

Writes web/data/cases/DEMO_FY2016_anon.json and adds (or refreshes) its row in
web/data/index.json, leaving every other case untouched.
"""

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from pecora.adversarial.bundle import attach_filing_spans  # noqa: E402
from pecora.adversarial.review import UNVERIFIED_PENALTY, Debate, summarize  # noqa: E402
from pecora.adversarial.verifier import verify_debate_quotes  # noqa: E402
from pecora.ingestion.sections import detect_sections  # noqa: E402

CASE_ID = "DEMO_FY2016_anon"
DATA_DIR = os.path.join(ROOT, "web", "data")


def ev(pid, section, text):
    return {"id": pid, "section": section, "text": text}


# The fictional filing, already anonymized the way the pipeline would mask a real one.
# Every evidence passage below is cut from this text, so quotes highlight in context.
FILING = """ANNUAL REPORT ON FORM 10-K
For the fiscal year ended December 31, 2016
[COMPANY] (sample data: a fictional company)

Item 1. Business

[COMPANY] designs, manufactures and services automated laboratory analyzer systems used by hospital networks, reference laboratories and research institutions. Our systems run blood chemistry, immunoassay and hematology panels, and we sell the consumable reagent kits and service contracts that keep them running.

We sell directly to large hospital networks in the United States and through independent distributors in Europe and Asia. A typical analyzer system sells for between $250,000 and $900,000, and larger orders often include installation, on-site validation and operator training. Our sales cycle for a new hospital network customer usually runs from nine to eighteen months.

Our research and development team is focused on our next generation analyzer platform, which we expect to begin shipping in volume during 2017. The new platform roughly doubles throughput per square foot of laboratory space and shares a common reagent catalog with our current systems.

We manufacture our systems at a single facility and rely on a small number of suppliers for precision optics and fluid handling components. We hold safety stock of these components, but a prolonged disruption at a key supplier could delay shipments.

As of December 31, 2016, we had approximately 1,140 full-time employees, of whom about 310 worked in research and development and about 260 in field service. None of our employees are represented by a labor union.

Our business is subject to regulation by the U.S. Food and Drug Administration and comparable agencies abroad. Our analyzer systems are cleared as medical devices, and changes to their design or intended use may require new clearances before we can sell them.

Item 1A. Risk Factors

Investing in our common stock involves risk. You should consider the risks described below together with the other information in this report.

A significant portion of our net sales is derived from a limited number of customers, and the loss of any of these customers could materially harm our business.

Our operating results may fluctuate significantly from quarter to quarter due to a variety of factors, many of which are outside of our control.

The timing of large system orders is difficult to predict. Hospital networks often make capital purchasing decisions near the end of their own budget periods, and a delay of a single large order can move a meaningful amount of revenue from one quarter to the next.

We depend on independent distributors for most of our international sales. Distributors may carry competing products, may reduce their purchases to manage their own inventory, and in some cases have the right to return or rotate stock.

Our new analyzer platform may not achieve market acceptance. If customers delay purchases of current systems while waiting for the new platform, our sales and margins could decline during the transition.

We are subject to extensive regulation, and failure to obtain or maintain clearances for our products could prevent us from selling them.

Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations

Overview. Net sales for 2016 were $412.6 million, an increase of 14% compared with 2015. Systems revenue grew 19% and consumables and service revenue grew 9%.

Net sales for the fourth quarter of 2016 increased 31% compared with the third quarter, driven primarily by shipments of laboratory analyzer systems to two hospital networks in the final ten days of the quarter. Of these shipments, a portion remained subject to customer acceptance testing at December 31, 2016.

Gross margin was 52.4% in 2016 compared with 53.1% in 2015, reflecting a higher mix of systems revenue, which carries lower margins than consumables.

Operating expenses increased 11%, primarily due to higher research and development spending on our next generation analyzer platform and additional field service staff.

Liquidity and capital resources. Cash and cash equivalents were $58.3 million at December 31, 2016. Accounts receivable increased to $121.7 million from $84.9 million a year earlier, reflecting the timing of fourth quarter shipments.

Inventories increased to $96.4 million at December 31, 2016 from $71.2 million at December 31, 2015, primarily to support anticipated demand for our next generation analyzer platform.

We believe our existing cash and our revolving credit facility will be sufficient to fund operations for at least the next twelve months.

Item 8. Financial Statements and Supplementary Data

Note 1. Basis of Presentation. The consolidated financial statements include the accounts of [COMPANY] and its wholly owned subsidiaries. All intercompany balances and transactions have been eliminated.

Note 2. Revenue Recognition. We recognize revenue when persuasive evidence of an arrangement exists, the product has been shipped, the price is fixed or determinable and collection is reasonably assured. For certain large system orders, we recognize revenue upon shipment where we believe customer acceptance provisions are perfunctory.

Revenue from service contracts is recognized ratably over the contract term. Revenue from consumables is recognized when shipped. For arrangements with multiple deliverables, we allocate revenue to each element based on its relative selling price.

Note 3. Accounts Receivable. Accounts receivable are stated net of an allowance for doubtful accounts of $1.9 million at December 31, 2016 and $1.6 million at December 31, 2015.

Note 4. Inventories. Inventories are stated at the lower of cost or market. Inventories include finished goods held at third-party logistics locations, including goods that we have committed to repurchase from certain distributors under stock rotation agreements.

Note 5. Commitments and Contingencies. We lease our manufacturing facility and several sales offices under operating leases expiring at various dates through 2024. From time to time we are involved in legal proceedings arising in the ordinary course of business.

Item 9A. Controls and Procedures

Our management, with the participation of our chief executive officer and chief financial officer, evaluated the effectiveness of our disclosure controls and procedures as of December 31, 2016.

Management identified a deficiency in the review of cut-off procedures for shipments near the end of the fiscal year. Management has concluded that this deficiency does not constitute a material weakness.

Based on that evaluation, our chief executive officer and chief financial officer concluded that our disclosure controls and procedures were effective at a reasonable assurance level. Management is enhancing the documentation and review of shipping records at period end.

There were no other changes in our internal control over financial reporting during the fourth quarter of 2016 that materially affected, or are reasonably likely to materially affect, our internal control over financial reporting.
"""


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
                {"responds_to": 2, "point": "The increase is modest and tied to a product launch, not to unsold goods.",
                 "passage_id": "E2",
                 "quote": "Inventories increased to $86.4 million at December 31, 2016 from $71.2 million at December 31, 2015, primarily to support anticipated demand"},
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


def place(evidence: list[dict]) -> list[dict]:
    """Give each passage its offsets in FILING and a section label, as the retriever would."""
    sections = detect_sections(FILING)
    for p in evidence:
        start = FILING.index(p["text"])
        sec = next(s for s in sections if s.start_char <= start < s.end_char)
        p.update(start=start, end=start + len(p["text"]), section=f"{sec.item_number} - {sec.name}")
    return evidence


def build() -> dict:
    debates = []
    for t in TRIALS:
        d = Debate(finding=t["finding"], evidence=place([dict(p) for p in t["evidence"]]), auditor=t["auditor"],
                   defender=t["defender"], adjudication=t["adjudication"])
        d.verdict = t["adjudication"]["verdict"]
        d.raw_confidence = t["adjudication"]["confidence"]
        d.citations = verify_debate_quotes(d.auditor, d.defender, d.adjudication, d.evidence)
        d.final_confidence = d.raw_confidence
        if not d.citations["decisive_verified"]:
            d.final_confidence = int(d.raw_confidence * UNVERIFIED_PENALTY)
            d.flags.append(f"decisive quote {d.citations['decisive_status']}: confidence halved")
        unverified = [c for c in d.citations["checks"] if not c["verified"]]
        if unverified:
            d.flags.append(f"{len(unverified)} quote(s) failed the check")
        debates.append(d)

    debate_dicts = [d.to_dict() for d in debates]
    bundle = attach_filing_spans(debate_dicts, FILING)
    filing = {"text": FILING, "sections": [{"name": s.name, "item_number": s.item_number,
                                            "start": s.start_char, "end": s.end_char}
                                           for s in detect_sections(FILING)]}

    # Suggested questions, answered offline. Quotes go through the same check as live answers.
    from pecora.ask import check_citation, collect_passages
    case = {"debates": debate_dicts}
    passages = collect_passages(case)
    by_text = {p["text"]: p["id"] for p in passages}
    qa = []
    for q, a, cites in DEMO_QA:
        cs = []
        for _, quote in cites:
            pid = next(by_text[t] for t in by_text if quote in t)
            c = check_citation(quote, pid, passages, FILING)
            assert c["status"] == "exact" and c["filing_spans"], (pid, quote, c["status"])
            cs.append(c)
        qa.append({"question": q, "answer": a, "citations": cs})

    summary = summarize(debates)
    return {
        "id": CASE_ID,
        "meta": {"ticker": "DEMO", "company_name": "Northwind Instruments (fictional)", "fiscal_year": 2016,
                 "filing_date": None, "report_date": "2016-12-31", "url": None, "anonymized": True,
                 "sample": True, "model": "sample case, no model call", "llm_calls": 0, "run_at": "sample",
                 "anonymization": {"aliases": ["Northwind Instruments"], "people": [], "products": [], "leaks": {}}},
        "summary": summary,
        "bundle": bundle,
        "screen": {"findings": 9, "failed_areas": {}},
        "debates": debate_dicts,
        "filing": filing,
        "demo_qa": qa,
    }


def index_row(case: dict) -> dict:
    m, s = case["meta"], case["summary"]
    return {"id": case["id"], "ticker": m["ticker"], "company_name": m["company_name"],
            "fiscal_year": m["fiscal_year"], "filing_date": m["filing_date"], "anonymized": m["anonymized"],
            "signal_score": s["signal_score"], "verdicts": s["verdicts"], "debated": len(case["debates"]),
            "screened": case["screen"]["findings"], "sample": True}


if __name__ == "__main__":
    case = build()
    os.makedirs(os.path.join(DATA_DIR, "cases"), exist_ok=True)
    with open(os.path.join(DATA_DIR, "cases", f"{CASE_ID}.json"), "w", encoding="utf-8") as f:
        json.dump(case, f)
    index_path = os.path.join(DATA_DIR, "index.json")
    index = json.load(open(index_path, encoding="utf-8")) if os.path.exists(index_path) else []
    index = [r for r in index if r.get("id") != CASE_ID] + [index_row(case)]
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1)
    s = case["summary"]
    print(f"Wrote {CASE_ID}: signal {s['signal_score']}, verdicts {s['verdicts']}, "
          f"quotes verified {s['citation_integrity']}, located {case['bundle']['located']}/{case['bundle']['citations']}")
