"""
Run Adversarial Review on one filing.

Usage:
    python -m pecora.adversarial.run --ticker SMCI --year 2016
    python -m pecora.adversarial.run --ticker SMCI --year 2016 --no-anonymize
    python -m pecora.adversarial.run --file data/x.txt --label DEMO --alias "Acme Corp"

Anonymization is ON by default: company names, ticker, and known executives
are masked before any agent sees the text.
"""

import argparse
import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from ..screen import Screener
from ..retrieval.focus_areas import FOCUS_AREAS
from ..ingestion.anonymizer import anonymize as anonymize_filing
from ..ingestion.chunker import chunk_sections
from ..ingestion.loader import load_from_file
from ..ingestion.sections import detect_sections
from .bundle import attach_filing_spans, filing_record
from .llm import make_llm
from .review import AdversarialReviewer, select_candidates, summarize

DEFAULT_FOCUS = ["revenue", "risk_factors", "litigation", "related_party"]


def run_adversarial(ticker: str | None = None, year: int | None = None, file_path: str | None = None,
                    label: str | None = None, anonymize: bool = True, mask_years: bool = False,
                    extra_aliases: list[str] | None = None, focus_areas: list[str] | None = None,
                    max_findings: int = 5, k_evidence: int = 5, workers: int = 3,
                    output_dir: str = "outputs/adversarial", llm=None, log=print) -> dict:
    # Heavy imports here so tests and the Streamlit viewer stay fast
    from ..retrieval.embedder import get_embedder
    from ..retrieval.retriever import Retriever
    from ..retrieval.vector_store import VectorStore

    focus_areas = focus_areas or DEFAULT_FOCUS
    meta = {"ticker": (ticker or label or "LOCAL").upper(), "fiscal_year": year,
            "anonymized": anonymize, "years_masked": mask_years,
            "run_at": datetime.now().isoformat(timespec="seconds")}

    log("[1/5] Loading filing...")
    company_name = None
    if file_path:
        text = load_from_file(file_path)
        meta["source"] = file_path
    else:
        from ..ingestion.edgar import fetch_10k
        doc = fetch_10k(ticker, year)
        text, company_name = doc["text"], doc["company_name"]
        meta.update({k: doc[k] for k in ("cik", "company_name", "filing_date", "report_date", "url")})
        meta["source"] = doc["url"]

    # Anonymize BEFORE anything reaches a model
    if anonymize:
        text, report = anonymize_filing(text, company_name, ticker, extra_aliases, mask_years)
        meta["anonymization"] = report
        log(f"[2/5] Anonymized: {len(report['aliases'])} company names, {len(report['people'])} people, "
              f"{len(report['products'])} products{', years' if mask_years else ''} masked; "
              f"leaks {report['leaks'] or 'none'}")
    else:
        log("[2/5] Anonymization OFF (look-ahead bias not controlled)")

    shown_name = "[COMPANY]" if anonymize else meta["ticker"]
    shown_year = "[YEAR]" if mask_years else str(year or "unknown")

    log("[3/5] Sectioning, chunking, embedding...")
    sections = detect_sections(text)
    chunks = chunk_sections(sections)
    embedder = get_embedder()
    store = VectorStore(dim=embedder.dim)
    store.add(chunks, embedder.embed_chunks([c.text for c in chunks]))
    retriever = Retriever(embedder, store)

    # Screener and agents share one LLM, so llm_calls counts every call in the run
    log("[4/5] Screening for candidate findings...")
    llm = llm or make_llm()
    screen = Screener(llm, log=log).run(ticker=shown_name, fiscal_year=shown_year,
                               retrieved_context=retriever.retrieve(focus_keys=focus_areas),
                               retriever=retriever, total_chunks=len(chunks))
    candidates = select_candidates(screen.findings, max_findings)
    log(f"      {len(screen.findings)} findings, {len(candidates)} sent to adversarial review")
    if screen.failed_areas:
        log(f"      Focus areas that failed: {list(screen.failed_areas)}")

    log(f"[5/5] Running Auditor / Defender / Adjudicator on {len(candidates)} findings...")
    reviewer = AdversarialReviewer(llm, retriever=retriever, k_evidence=k_evidence)
    debates = reviewer.review_all(
        [f.to_dict() for f in candidates], workers=workers,
        on_done=lambda d: log(f"      Trial done: {d.finding.get('title', '')} -> {d.verdict} {d.final_confidence}%"))
    debate_dicts = [d.to_dict() for d in debates]
    bundle = attach_filing_spans(debate_dicts, text)

    result = {"meta": {**meta, "model": getattr(llm, "model", "custom"),
                       "llm_transport": type(llm).__name__,
                       "llm_calls": getattr(llm, "calls", None),
                       "llm_tokens": {"input": getattr(llm, "input_tokens", None),
                                      "output": getattr(llm, "output_tokens", None)}},
              "summary": summarize(debates),
              "screen": {"findings": [f.to_dict() for f in screen.findings],
                         "debated": [i for i, f in enumerate(screen.findings)
                                     if any(f is c for c in candidates)],
                         "failed_areas": screen.failed_areas},
              "debates": debate_dicts,
              "bundle": bundle,
              "filing": filing_record(text, sections)}

    os.makedirs(output_dir, exist_ok=True)
    fy = f"FY{year}" if year else "local"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(output_dir, f"{meta['ticker']}_{fy}{'_anon' if anonymize else ''}_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    result["path"] = path

    s = result["summary"]
    signal = "n/a" if s["signal_score"] is None else f"{s['signal_score']}/100"
    log(f"\n  Signal score: {signal}   Verdicts: {s['verdicts']}"
          f"   Citation integrity: {s['citation_integrity']}")
    m = result["meta"]
    log(f"  LLM: {m['llm_transport']} {m['model']}, {m['llm_calls']} calls, "
          f"tokens in/out {m['llm_tokens']['input']}/{m['llm_tokens']['output']}")
    log(f"  Quotes located in filing: {bundle['located']}/{bundle['citations']}, exact quotes confirmed "
          f"{bundle['exact_confirmed']}, mismatches {len(bundle['mismatches'])}")
    log(f"  Saved -> {path}")
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pecora.ai: adversarial review of SEC filings")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--ticker")
    src.add_argument("--file")
    p.add_argument("--year", type=int)
    p.add_argument("--label", help="Name for a local-file run")
    p.add_argument("--alias", action="append", default=[], help="Extra name to mask (repeatable)")
    p.add_argument("--no-anonymize", action="store_true")
    p.add_argument("--mask-years", action="store_true")
    p.add_argument("--focus", nargs="+", default=DEFAULT_FOCUS, choices=list(FOCUS_AREAS))
    p.add_argument("--max-findings", type=int, default=5)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--output-dir", default="outputs/adversarial")
    return p


def main():
    args = build_parser().parse_args()
    if args.ticker and not args.year:
        sys.exit("--year is required with --ticker")
    run_adversarial(ticker=args.ticker, year=args.year, file_path=args.file, label=args.label,
                    anonymize=not args.no_anonymize, mask_years=args.mask_years,
                    extra_aliases=args.alias, focus_areas=args.focus,
                    max_findings=args.max_findings, workers=args.workers,
                    output_dir=args.output_dir)


if __name__ == "__main__":
    main()
