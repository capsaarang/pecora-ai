"""
Sweep SEC staff comment letters (UPLOAD) across many tickers.

For each ticker: fetch every UPLOAD letter since 2005, keep the ones that review a
10-K, split them into numbered comments, tag each comment's topic, and record which
fiscal year was reviewed. Writes sweep_results.json and sweep_comments.csv.

Usage: python letter_sweep.py [TICKER ...]   (defaults to the list below)
"""
import csv, io, json, os, re, sys, time
sys.path.insert(0, "/Users/markaashish/Desktop/My Projects/Mad Hacks/pecora-ai")
from dotenv import load_dotenv
load_dotenv("/Users/markaashish/Desktop/My Projects/Mad Hacks/pecora-ai/.env")
import pdfplumber
from bs4 import BeautifulSoup
from pecora.ingestion.edgar import _session

HERE = os.path.dirname(os.path.abspath(__file__))
DL = os.path.join(HERE, "letters_dl")
os.makedirs(DL, exist_ok=True)

# Companies with later accounting trouble (verify each case yourself) + peers
TROUBLED = ["SMCI", "MDXG", "SNCR", "UA", "KHC", "GE", "BHC", "HTZ", "TSLA", "NKLA"]
PEERS = ["NTAP", "HPE", "DELL", "PSTG", "CSCO", "IBM", "ANET", "NTNX", "WDC", "STX",
         "NKE", "LULU", "SKX", "KO", "PEP", "GIS", "CAG", "MDT", "ABT", "BSX",
         "HON", "MMM", "EMR", "CAR", "URI", "ORCL", "ADBE", "CRM", "INTC", "AMD",
         "NVDA", "QCOM", "TXN", "AAPL", "AMZN"]

TOPICS = [  # first match wins, so order matters
    ("revenue", r"revenue recogni|multiple.element|deferred revenue|sell-in|sell-through|distributor|channel|returns? reserve|bill.and.hold|performance obligation|ASC 606|VSOE"),
    ("related_party", r"related.part|affiliate[sd]? (?:of|transactions)"),
    ("controls", r"material weakness|internal control|disclosure controls"),
    ("restatement_error", r"restate|error|immaterial correction|out.of.period"),
    ("impairment", r"impairment|goodwill|write-?down"),
    ("segments", r"segment|ASC 280|operating segments?"),
    ("non_gaap", r"non-?GAAP"),
    ("receivables_inventory", r"receivable|allowance for doubtful|inventor(?:y|ies)|DSO"),
    ("estimates_reserves", r"critical accounting|estimate|reserve|warranty|contingenc|ASC 450"),
    ("tax", r"income tax|tax rate|valuation allowance|undistributed"),
    ("liquidity_mda", r"liquidity|capital resources|MD&A|results of operations|known trends"),
    ("compensation", r"compensation|bonus|peer group|named executive"),
    ("sanctions", r"Iran|Sudan|Syria|Cuba|North Korea"),
]
ACCOUNTING = {"revenue", "related_party", "controls", "restatement_error", "impairment", "segments",
              "non_gaap", "receivables_inventory", "estimates_reserves", "tax", "liquidity_mda"}
FOLLOWUP = re.compile(r"^(?:we note|in|based (?:up)?on)?\s*(?:your|the)?\s*response to (?:our )?(?:prior )?comment|^your response to", re.I)
FY_RE = re.compile(r"Form\s+10-K(?:/A)?\s+for\s+the\s+(?:fiscal\s+)?(?:year|period)\s+ended\s+([A-Z][a-z]+\s+\d{1,2},\s+(\d{4}))", re.I)

s = _session()


def get(url, binary=False):
    time.sleep(0.12)
    r = s.get(url, timeout=60)
    r.raise_for_status()
    return r.content if binary else r.json()


def letter_text(path):
    if path.lower().endswith(".pdf"):
        try:
            with pdfplumber.open(path) as pdf:
                return "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception:
            return ""
    raw = open(path, "rb").read().decode("utf-8", "ignore")
    return BeautifulSoup(raw, "lxml").get_text("\n") if "<" in raw[:2000] else raw


def split_comments(text):
    parts = re.split(r"(?m)^\s*(\d{1,2})\.\s+", text)
    out, expect = [], 1
    for i in range(1, len(parts) - 1, 2):
        n = int(parts[i])
        if n == expect:  # numbered comments run 1, 2, 3...; skips page numbers and list items
            out.append(re.sub(r"\s+", " ", parts[i + 1]).strip()[:1500])
            expect += 1
    return out


def topic(c):
    for name, pat in TOPICS:
        if re.search(pat, c, re.I):
            return name
    return "other"


tickers = sys.argv[1:] or TROUBLED + PEERS
cmap = {v["ticker"]: v["cik_str"] for v in get("https://www.sec.gov/files/company_tickers.json").values()}
results, rows = {}, []
for t in tickers:
    cik = cmap.get(t)
    if not cik:
        print(f"{t}: not in SEC ticker map, skipped", flush=True)
        continue
    sub = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    blocks = [sub["filings"]["recent"]] + [get(f"https://data.sec.gov/submissions/{f['name']}")
                                           for f in sub["filings"].get("files", [])]
    letters = [(d, a, doc) for b in blocks
               for form, d, a, doc in zip(b["form"], b["filingDate"], b["accessionNumber"], b["primaryDocument"])
               if form == "UPLOAD" and d >= "2005"]
    rec = {"name": sub["name"], "cik": cik, "uploads": len(letters), "tenk_letters": 0,
           "reviewed_fys": {}, "initial_comments": 0, "accounting_comments": 0}
    for d, a, doc in sorted(letters):
        path = os.path.join(DL, f"{t}_{d}_{a}_{doc}")
        if not os.path.exists(path):
            try:
                open(path, "wb").write(get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{a.replace('-', '')}/{doc}", True))
            except Exception as e:
                print(f"  {t} {d}: download failed {e}", flush=True)
                continue
        text = letter_text(path)
        m = FY_RE.search(text[:4000])
        if not m:
            continue  # S-1, proxy, tender offer, 10-Q-only or unreadable
        fy = m.group(2)
        rec["tenk_letters"] += 1
        comments = split_comments(text)
        initial = [c for c in comments if not FOLLOWUP.search(c[:160])]
        fyrec = rec["reviewed_fys"].setdefault(fy, {"letters": 0, "initial": 0, "topics": {}})
        fyrec["letters"] += 1
        fyrec["initial"] += len(initial)
        for c in initial:
            tp = topic(c)
            fyrec["topics"][tp] = fyrec["topics"].get(tp, 0) + 1
            rec["initial_comments"] += 1
            rec["accounting_comments"] += tp in ACCOUNTING
            rows.append({"ticker": t, "letter_date": d, "accession": a, "fy_reviewed": fy, "topic": tp, "comment": c})
    results[t] = rec
    print(f"{t:5} uploads={rec['uploads']:>3}  10-K letters={rec['tenk_letters']:>3}  "
          f"10-K years reviewed={len(rec['reviewed_fys']):>2}  initial comments={rec['initial_comments']:>3}  "
          f"accounting={rec['accounting_comments']:>3}", flush=True)

json.dump(results, open(os.path.join(HERE, "sweep_results.json"), "w"), indent=1)
with open(os.path.join(HERE, "sweep_comments.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["ticker", "letter_date", "accession", "fy_reviewed", "topic", "comment"])
    w.writeheader()
    w.writerows(rows)

tot = {}
for r in rows:
    tot[r["topic"]] = tot.get(r["topic"], 0) + 1
print(f"\nTOTAL companies={len(results)}  10-K reviews (company-years)={sum(len(r['reviewed_fys']) for r in results.values())}  "
      f"initial comments={len(rows)}  accounting={sum(r['accounting_comments'] for r in results.values())}")
print("by topic:", dict(sorted(tot.items(), key=lambda kv: -kv[1])))
