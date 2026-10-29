"""
Peer distributions: where does one filing sit among its industry on each red-flag metric?

Usage:
    python -m pecora.quant.peers --ticker MDXG --year 2016
    python -m pecora.quant.peers --ticker SMCI --year 2016 --min-peers 30

For each metric the output gives the company's value, its percentile among peers, a robust
z-score (median / MAD), a one-sided empirical p-value in the red-flag direction, and a
Benjamini-Hochberg q-value across all metrics, so testing 8 metrics does not manufacture
a "significant" one.

Peers are filers with the same 4-digit SIC code, widened to the 3-digit code and then to all
filers if fewer than --min-peers have data. Peer numbers come from SEC frames (latest filed,
calendar-aligned); the company's numbers come from its original 10-K only.
"""

import argparse
import json
import os
from datetime import datetime

import numpy as np
from dotenv import load_dotenv

from ..ingestion.edgar import _session
from .metrics import BENEISH_CUTOFF, METRICS, beneish_m, compute_all
from .xbrl import CONCEPTS, company_values, frame_values, peer_ciks

MIN_PEER_REVENUE = 10_000_000  # drop shells and pre-revenue companies from the reference set
FLAG_Q = 0.10


def peer_table(year: int, session=None) -> dict[int, dict]:
    """{cik: {"t": {item: value}, "t1": {...}}} for every filer with data in calendar year `year`."""
    table: dict[int, dict] = {}
    for item in CONCEPTS:
        for key, y in (("t", year), ("t1", year - 1)):
            for cik, val in frame_values(item, y, session).items():
                table.setdefault(cik, {"t": {}, "t1": {}})[key][item] = val
    return {cik: v for cik, v in table.items()
            if v["t"].get("revenue", 0) >= MIN_PEER_REVENUE and v["t1"].get("revenue", 0) > 0}


def choose_peers(sic: str, available: set[int], exclude: int, min_peers: int, session=None):
    """(tier, ciks): same 4-digit SIC, else same 3-digit SIC, else all filers."""
    if sic:
        four = (peer_ciks(sic, session) & available) - {exclude}
        if len(four) >= min_peers:
            return f"SIC {sic}", four
        three = set()
        for d in range(10):
            three |= peer_ciks(f"{sic[:3]}{d}", session)
        three = (three & available) - {exclude}
        if len(three) >= min_peers:
            return f"SIC {sic[:3]}x", three
    return "all filers", available - {exclude}


def benjamini_hochberg(pvals: dict[str, float]) -> dict[str, float]:
    """BH-adjusted q-values: the false discovery rate if every metric at or below this q is flagged."""
    names = sorted(pvals, key=pvals.get)
    m, q, running = len(names), {}, 1.0
    for rank in range(m, 0, -1):
        name = names[rank - 1]
        running = min(running, pvals[name] * m / rank)
        q[name] = running
    return q


def position(value: float, peers: np.ndarray, direction: str) -> dict:
    """Percentile, robust z and one-sided empirical p-value of `value` within `peers`."""
    below, ties = np.sum(peers < value), np.sum(peers == value)
    median = float(np.median(peers))
    mad = float(np.median(np.abs(peers - median))) * 1.4826
    extreme = np.sum(peers >= value) if direction == "high" else np.sum(peers <= value)
    return {"percentile": round(100 * (below + 0.5 * ties) / len(peers), 1),
            "robust_z": round((value - median) / mad, 2) if mad else None,
            "p_value": (1 + int(extreme)) / (len(peers) + 1),  # +1: the company counts as one draw
            "peer_median": median}


def analyze(ticker: str, year: int, min_peers: int = 25) -> dict:
    session = _session()
    company = company_values(ticker, year, session)
    cy = company["calendar_year"]
    table = peer_table(cy, session)
    tier, ciks = choose_peers(company["sic"], set(table), company["cik"], min_peers, session)
    peer_metrics = {cik: compute_all(table[cik]["t"], table[cik]["t1"]) for cik in ciks}
    values = compute_all(company["t"], company["t1"])

    metrics, pvals = [], {}
    for name, (label, _, direction) in METRICS.items():
        dist = np.array([m[name] for m in peer_metrics.values() if m[name] is not None], dtype=float)
        dist = dist[np.isfinite(dist)]
        row = {"name": name, "label": label, "direction": direction, "value": values[name],
               "peer_n": int(dist.size), "distribution": dist.round(4).tolist()}
        if values[name] is not None and dist.size >= 10:
            row.update(position(values[name], dist, direction))
            pvals[name] = row["p_value"]
        metrics.append(row)
    qvals = benjamini_hochberg(pvals) if pvals else {}
    for row in metrics:
        row["q_value"] = qvals.get(row["name"])
        row["flagged"] = row["q_value"] is not None and row["q_value"] <= FLAG_Q

    m, comps, imputed = beneish_m(company["t"], company["t1"])
    return {
        "meta": {"ticker": company["ticker"], "name": company["name"], "fiscal_year": year,
                 "period": [company["period_start"], company["period_end"]], "calendar_year": cy,
                 "frame_source": company["frame_source"],
                 "accession": company["accession"], "sic": company["sic"], "peer_group": tier,
                 "peers": len(ciks), "min_peer_revenue": MIN_PEER_REVENUE, "flag_q": FLAG_Q,
                 "run_at": datetime.now().isoformat(timespec="seconds")},
        "company": {"t": company["t"], "t1": company["t1"], "tags": company["tags"]},
        "beneish": {"m": m, "cutoff": BENEISH_CUTOFF, "components": comps, "imputed": imputed,
                    "above_cutoff": m is not None and m > BENEISH_CUTOFF},
        "metrics": metrics,
    }


def _fmt(v, digits=3):
    return "n/a" if v is None else f"{v:.{digits}f}"


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description="Pecora.ai: peer distributions from SEC XBRL")
    p.add_argument("--ticker", required=True)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--min-peers", type=int, default=25)
    p.add_argument("--output-dir", default="outputs/quant")
    args = p.parse_args()

    r = analyze(args.ticker.upper(), args.year, args.min_peers)
    m = r["meta"]
    print(f"\n{m['name']} FY{m['fiscal_year']} ({m['period'][0]} to {m['period'][1]}, frames CY{m['calendar_year']})")
    print(f"Peers: {m['peer_group']}, n={m['peers']} with revenue >= ${MIN_PEER_REVENUE / 1e6:.0f}M\n")
    print(f"  {'metric':38s} {'value':>9s} {'median':>9s} {'pctile':>7s} {'z':>6s} {'p':>7s} {'q':>7s}  n")
    for row in r["metrics"]:
        flag = "  <- flagged" if row["flagged"] else ""
        print(f"  {row['label']:38s} {_fmt(row['value']):>9s} {_fmt(row.get('peer_median')):>9s} "
              f"{_fmt(row.get('percentile'), 1):>7s} {_fmt(row.get('robust_z'), 2):>6s} "
              f"{_fmt(row.get('p_value')):>7s} {_fmt(row['q_value']):>7s}  {row['peer_n']}{flag}")
    b = r["beneish"]
    print(f"\n  Beneish M = {_fmt(b['m'], 2)} (cutoff {b['cutoff']}; "
          f"{'ABOVE' if b['above_cutoff'] else 'below'})"
          f"{'  imputed as 1.0: ' + ', '.join(b['imputed']) if b['imputed'] else ''}")

    os.makedirs(args.output_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(args.output_dir, f"{m['ticker']}_FY{m['fiscal_year']}_peers_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=1)
    print(f"  Saved -> {path}")


if __name__ == "__main__":
    main()
