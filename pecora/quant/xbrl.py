"""
SEC XBRL data: one company's numbers as originally filed, and every filer's numbers for a period.

  - company_values(): reads companyfacts and keeps ONLY facts from the original 10-K's
    accession, so a later restatement can never leak hindsight into the company's numbers.
  - frame_values(): the SEC frames API returns one value per filer for a calendar period.
    Frames hold each filer's LATEST filed value, so peers may include restated numbers.
  - peer_ciks(): companies sharing a SIC code, from EDGAR's company browse.

Everything is cached on disk under data/cache/xbrl/.
"""

import json
import os
import re
from datetime import date

from ..ingestion.edgar import _get, _session, list_10k_filings, resolve_cik, select_filing

CACHE_DIR = os.path.join("data", "cache", "xbrl")

# Each line item lists the us-gaap tags filers use for it, in priority order
CONCEPTS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "SalesRevenueGoodsNet", "RevenueFromContractWithCustomerIncludingAssessedTax",
                "SalesRevenueServicesNet"],
    "cogs": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "receivables": ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
    "inventory": ["InventoryNet"],
    "net_income": ["IncomeLossFromContinuingOperations", "NetIncomeLoss", "ProfitLoss"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "total_assets": ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "ppe": ["PropertyPlantAndEquipmentNet"],
    "depreciation": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "Depreciation"],
    "sga": ["SellingGeneralAndAdministrativeExpense"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "deferred_revenue": ["DeferredRevenueCurrent", "ContractWithCustomerLiabilityCurrent"],
}
INSTANT = {"receivables", "inventory", "total_assets", "current_assets", "ppe",
           "current_liabilities", "long_term_debt", "deferred_revenue"}


def _cached_json(session, url: str, path: str):
    """GET a JSON URL once; later calls read the cached copy. A 404 is cached as None."""
    full = os.path.join(CACHE_DIR, path)
    if os.path.exists(full):
        with open(full, encoding="utf-8") as f:
            return json.load(f)
    try:
        data = _get(session, url, as_json=True)
    except Exception as e:
        if getattr(getattr(e, "response", None), "status_code", None) != 404:
            raise
        data = None  # this concept has no frame for this period
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def calendar_year(start: str, end: str) -> int:
    """SEC frame rule for annual periods: the calendar year with the most overlap, ties to the later year."""
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if s.year == e.year:
        return e.year
    first = (date(s.year, 12, 31) - s).days + 1
    second = (e - date(e.year, 1, 1)).days + 1
    return s.year if first > second else e.year


def company_values(ticker: str, fiscal_year: int, session=None) -> dict:
    """
    Line items for the fiscal year (t) and the prior year (t1), from the original 10-K only.

    Returns {"ticker", "cik", "name", "sic", "accession", "period_start", "period_end",
             "calendar_year", "t": {item: value}, "t1": {item: value}, "tags": {item: tag}}.
    """
    session = session or _session()
    cik = resolve_cik(ticker, session)
    name, filings = list_10k_filings(cik, session)
    filing = select_filing(filings, fiscal_year)
    if not filing:
        raise ValueError(f"No original 10-K for {ticker} FY{fiscal_year}")
    accn, report_end = filing["accession"], filing["report_date"]

    facts = _cached_json(session, f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
                         f"companyfacts/CIK{cik:010d}.json")
    sub = _cached_json(session, f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
                       f"submissions/CIK{cik:010d}.json")
    if not facts or "us-gaap" not in facts.get("facts", {}):
        raise ValueError(f"No XBRL data for {ticker}. Filings before about 2010 have none.")
    gaap = facts["facts"]["us-gaap"]

    def from_original(tag: str) -> list[dict]:
        return [f for unit, rows in gaap.get(tag, {}).get("units", {}).items() if unit == "USD"
                for f in rows if f.get("accn") == accn]

    out = {"ticker": ticker.upper(), "cik": cik, "name": name, "sic": str(sub.get("sic") or ""),
           "accession": accn, "t": {}, "t1": {}, "tags": {}}
    period = None
    for item, tags in CONCEPTS.items():
        for tag in tags:
            rows = from_original(tag)
            if item in INSTANT:
                cur = [f for f in rows if abs(_days(report_end, f["end"])) <= 7]
                prev = [f for f in rows if abs(_days(f["end"], report_end) - 365) <= 10]
            else:  # a full fiscal year, not a quarter
                annual = [f for f in rows if "start" in f and 350 <= _days(f["start"], f["end"]) <= 380]
                cur = [f for f in annual if abs(_days(report_end, f["end"])) <= 7]
                prev = [f for f in annual if abs(_days(f["end"], report_end) - 365) <= 10]
            if cur:
                out["t"][item] = cur[0]["val"]
                out["tags"][item] = tag
                if prev:
                    out["t1"][item] = prev[0]["val"]
                if item == "revenue":
                    period = (cur[0]["start"], cur[0]["end"])
                break
    if "revenue" not in out["t"]:
        raise ValueError(f"{ticker} FY{fiscal_year}: no revenue fact in the original 10-K ({accn})")
    out["period_start"], out["period_end"] = period
    # Use the frame SEC itself assigned this period to (carried on a later filing's copy of
    # the fact), so peers come from the same frame the company sits in
    assigned = [f["frame"] for f in gaap[out["tags"]["revenue"]]["units"].get("USD", [])
                if f.get("start") == period[0] and f.get("end") == period[1]
                and re.fullmatch(r"CY\d{4}", f.get("frame", ""))]
    out["calendar_year"] = int(assigned[0][2:]) if assigned else calendar_year(*period)
    out["frame_source"] = "SEC assignment" if assigned else "max-overlap rule"
    return out


def frame_values(item: str, year: int, session=None) -> dict[int, float]:
    """{cik: value} for one line item in calendar year `year`, first tag in priority order wins."""
    session = session or _session()
    period = f"CY{year}Q4I" if item in INSTANT else f"CY{year}"
    values: dict[int, float] = {}
    for tag in CONCEPTS[item]:
        data = _cached_json(session, f"https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/{period}.json",
                            f"frames/{tag}_{period}.json")
        for row in (data or {}).get("data", []):
            values.setdefault(int(row["cik"]), row["val"])
    return values


def peer_ciks(sic: str, session=None) -> set[int]:
    """Every company EDGAR lists under one SIC code (current assignment, active or not)."""
    session = session or _session()
    path = os.path.join(CACHE_DIR, "sic", f"{sic}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return set(json.load(f))
    ciks, start = set(), 0
    while True:
        url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=10-K&owner=include"
               f"&count=100&output=atom&SIC={sic}&start={start}")
        page = _get(session, url)
        found = {int(c) for c in re.findall(r"<cik>(\d+)</cik>", page)}
        ciks |= found
        if len(found) < 100:
            break
        start += 100
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(ciks), f)
    return ciks
