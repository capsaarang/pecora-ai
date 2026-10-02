"""
SEC EDGAR fetcher

Fixes over the v1 loader:
  - Walks the full paginated filing history (older 10-Ks are not in "recent")
  - Selects by fiscal-year REPORT date, so June fiscal years (e.g. SMCI) work
  - Returns ORIGINAL 10-Ks only, never 10-K/A: the text investors saw at the time
  - Parses HTML with BeautifulSoup and drops hidden inline-XBRL blocks
  - Uses a real contact email in the User-Agent, as SEC requires

Set SEC_EMAIL in your environment or .env file.
"""

import os
import re
import time

import requests
from bs4 import BeautifulSoup

# Known CIKs, so demo cases never depend on the live ticker map
CIK_OVERRIDES = {
    "SMCI": 1375365,   # Super Micro Computer
    "NTAP": 1002047,   # NetApp
    "GVA": 861459,     # Granite Construction
}

_RATE_LIMIT_SECONDS = 0.15  # SEC allows about 10 requests per second


def _session() -> requests.Session:
    email = os.environ.get("SEC_EMAIL")
    if not email:
        raise ValueError("SEC_EMAIL is not set. SEC requires a contact email in the User-Agent.")
    s = requests.Session()
    s.headers.update({"User-Agent": f"Pecora.ai research {email}",
                      "Accept-Encoding": "gzip, deflate"})
    return s


def _get(session: requests.Session, url: str, as_json: bool = False):
    time.sleep(_RATE_LIMIT_SECONDS)
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.json() if as_json else r.text


def resolve_cik(ticker: str, session: requests.Session | None = None) -> int:
    ticker = ticker.upper()
    if ticker in CIK_OVERRIDES:
        return CIK_OVERRIDES[ticker]
    session = session or _session()
    data = _get(session, "https://www.sec.gov/files/company_tickers.json", as_json=True)
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker:
            return int(entry["cik_str"])
    raise ValueError(f"Could not resolve CIK for ticker {ticker}. Add it to CIK_OVERRIDES.")


def list_10k_filings(cik: int, session: requests.Session | None = None) -> tuple[str, list[dict]]:
    """Return (company_name, original 10-K filings) across the full filing history."""
    session = session or _session()
    data = _get(session, f"https://data.sec.gov/submissions/CIK{cik:010d}.json", as_json=True)
    blocks = [data["filings"]["recent"]]
    for extra in data["filings"].get("files", []):
        blocks.append(_get(session, f"https://data.sec.gov/submissions/{extra['name']}", as_json=True))

    filings = []
    for b in blocks:
        for form, acc, doc, rdate, fdate in zip(b["form"], b["accessionNumber"],
                                                b["primaryDocument"], b["reportDate"],
                                                b["filingDate"]):
            if form == "10-K":
                filings.append({"accession": acc, "primary_doc": doc,
                                "report_date": rdate, "filing_date": fdate})
    return data.get("name", ""), filings


def select_filing(filings: list[dict], fiscal_year: int) -> dict | None:
    """Pick the original 10-K whose fiscal period ends in fiscal_year."""
    matches = [f for f in filings if (f["report_date"] or "").startswith(str(fiscal_year))]
    if not matches:
        return None
    return sorted(matches, key=lambda f: f["filing_date"])[0]  # earliest = original


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all(style=re.compile(r"display:\s*none", re.I)):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def fetch_10k(ticker: str, fiscal_year: int) -> dict:
    """
    Fetch one original 10-K.

    Returns dict with: text, company_name, cik, ticker, fiscal_year,
    filing_date, report_date, url
    """
    session = _session()
    cik = resolve_cik(ticker, session)
    company_name, filings = list_10k_filings(cik, session)
    filing = select_filing(filings, fiscal_year)
    if not filing:
        years = sorted({f["report_date"][:4] for f in filings if f["report_date"]})
        raise ValueError(f"No original 10-K for {ticker} FY{fiscal_year}. Available: {years}")

    url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/"
           f"{filing['accession'].replace('-', '')}/{filing['primary_doc']}")
    print(f"[EDGAR] {ticker} FY{fiscal_year}: filed {filing['filing_date']} -> {url}")
    raw = _get(session, url)
    text = html_to_text(raw) if "<" in raw[:2000] else raw

    return {"text": text, "company_name": company_name, "cik": cik,
            "ticker": ticker.upper(), "fiscal_year": fiscal_year,
            "filing_date": filing["filing_date"], "report_date": filing["report_date"],
            "url": url}
