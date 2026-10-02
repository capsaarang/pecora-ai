"""
Audit focus areas and their retrieval queries.

Each focus area maps to a set of semantic queries used to retrieve
relevant chunks from the 10-K via vector similarity search.
"""

FOCUS_AREAS = {
    "risk_factors": {
        "label": "Risk Factors",
        "section_hints": ["Item 1A", "Risk Factors"],
        "queries": [
            "material risks that could adversely affect business operations",
            "risks related to competition market share revenue decline",
            "regulatory legal compliance risks",
            "macroeconomic geopolitical risks supply chain",
            "technology cybersecurity data breach risks",
            "concentration risk single customer supplier product",
            "risks may cause actual results to differ materially",
        ],
        "audit_instructions": (
            "Identify risks that are vague, boilerplate, or insufficiently disclosed. "
            "Flag any risks that appear understated relative to industry norms. "
            "Note if the company added new risk factors not present in prior year. "
            "Look for concentration risks, tail risks, or emerging risks buried in generic language."
        ),
    },
    "revenue": {
        "label": "Revenue Anomalies",
        "section_hints": ["Item 7", "MD&A", "Revenue", "Net sales"],
        "queries": [
            "revenue recognition policy changes",
            "net revenue net sales year over year growth decline",
            "deferred revenue contract liabilities backlog",
            "revenue concentration single customer segment",
            "channel stuffing pull-forward demand",
            "non-GAAP adjusted revenue reconciliation",
            "revenue by geography segment product line breakdown",
            "unbilled receivables accounts receivable days outstanding",
        ],
        "audit_instructions": (
            "Flag unusual revenue recognition policies or recent changes. "
            "Identify if revenue growth diverges significantly from industry peers. "
            "Look for signs of pull-forward demand, channel stuffing, or aggressive recognition. "
            "Flag large deferred revenue buildups or unusual AR trends. "
            "Note any non-GAAP adjustments that materially inflate reported revenue."
        ),
    },
    "debt": {
        "label": "Debt & Liquidity",
        "section_hints": ["Item 7", "Liquidity", "Capital Resources", "Long-term debt", "Note"],
        "queries": [
            "long-term debt total debt outstanding maturity schedule",
            "credit facility revolving credit debt covenants",
            "cash and cash equivalents liquidity position",
            "interest expense coverage ratio debt service",
            "leverage ratio net debt EBITDA",
            "refinancing risk debt maturity wall",
            "going concern substantial doubt ability to continue",
            "free cash flow capital expenditure working capital",
        ],
        "audit_instructions": (
            "Flag high leverage ratios, near-term debt maturities, or tight covenant headroom. "
            "Identify any going concern language or substantial doubt disclosures. "
            "Look for deteriorating free cash flow relative to debt service obligations. "
            "Flag off-balance-sheet liabilities, operating lease obligations, or hidden debt structures. "
            "Note if liquidity position is deteriorating versus prior year."
        ),
    },
    "litigation": {
        "label": "Litigation Exposure",
        "section_hints": ["Item 3", "Legal Proceedings", "Commitments and Contingencies", "Note"],
        "queries": [
            "legal proceedings lawsuits pending litigation",
            "class action securities fraud lawsuit settlement",
            "regulatory investigation SEC DOJ FTC antitrust",
            "contingent liabilities loss contingency accrual",
            "intellectual property patent infringement dispute",
            "environmental liability remediation costs",
            "employment discrimination labor dispute",
        ],
        "audit_instructions": (
            "Flag material litigation where outcomes are uncertain or losses probable but unquantified. "
            "Identify regulatory investigations that could result in significant fines or operational restrictions. "
            "Look for new litigation added since the prior year filing. "
            "Flag cases where the company says a loss is 'reasonably possible' but provides no range. "
            "Note any settlements that represent a meaningful percentage of net income."
        ),
    },
    "related_party": {
        "label": "Related-Party Transactions",
        "section_hints": ["Related Party", "Note", "Transactions with"],
        "queries": [
            "related party transactions officers directors",
            "transactions with affiliated entities subsidiaries",
            "executive compensation loans to officers",
            "board member business relationships conflicts of interest",
            "founder family member transactions",
            "intercompany transactions transfer pricing",
        ],
        "audit_instructions": (
            "Flag any related-party transactions that appear to benefit insiders at shareholder expense. "
            "Identify transactions not conducted at arm's length. "
            "Look for unusual compensation arrangements, loans to executives, or self-dealing. "
            "Note if disclosure is vague or if amounts are material relative to revenue or net income. "
            "Flag any new related-party relationships not disclosed in prior year."
        ),
    },
    "forward_guidance": {
        "label": "Forward Guidance",
        "section_hints": ["Item 7", "Outlook", "Forward-looking", "Guidance"],
        "queries": [
            "forward-looking statements assumptions future results",
            "management outlook guidance fiscal year expectations",
            "growth assumptions market expansion projections",
            "safe harbor forward-looking cautionary statements",
            "factors that could cause results to differ materially",
            "capital allocation priorities share buyback dividend",
        ],
        "audit_instructions": (
            "Identify if forward-looking statements rely on aggressive or unsupported assumptions. "
            "Flag if guidance is significantly more optimistic than recent trend lines suggest. "
            "Look for vague or hedged language that obscures actual expectations. "
            "Note if prior-year guidance proved materially inaccurate with no explanation. "
            "Flag any changes in tone or specificity of guidance relative to prior filings."
        ),
    },
}


def get_focus_area(key: str) -> dict:
    if key not in FOCUS_AREAS:
        raise ValueError(f"Unknown focus area: {key}. Valid: {list(FOCUS_AREAS.keys())}")
    return FOCUS_AREAS[key]


def get_all_queries(focus_keys: list[str]) -> list[tuple[str, str]]:
    """Return (focus_key, query) pairs for all selected focus areas."""
    pairs = []
    for key in focus_keys:
        area = get_focus_area(key)
        for q in area["queries"]:
            pairs.append((key, q))
    return pairs
