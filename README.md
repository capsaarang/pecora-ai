# Pecora.ai

**AI findings you can argue with.**
Adversarial AI review of SEC 10-K filings.

## Why "Pecora"

In 1933, Ferdinand Pecora, chief counsel to the US Senate Banking Committee, cross-examined Wall Street's most powerful bankers after the 1929 crash. His hearings exposed widespread abuse and led to the Securities Acts of 1933 and 1934, which created the SEC. Pecora.ai cross-examines the filings his work brought into existence.

## The problem

AI can scan a 100-page annual report in seconds and flag risks. But a single model tends to agree with whatever it is asked, misreads standard boilerplate as a warning sign, and sometimes invents quotes. If you cannot verify where a finding came from, you cannot act on it.

## Our approach

We don't ask whether AI can find red flags. We measure whether its findings can be trusted.

Every candidate finding goes on trial:

- **Auditor** argues the finding is a genuine red flag, citing exact passages.
- **Defender** argues the company's side using the same evidence, and concedes what it cannot rebut.
- **Adjudicator** rules UPHELD, DISMISSED, or INCONCLUSIVE, assigns a 0-100 confidence, and cites the decisive passage.

Then code, not AI, checks every quote against the filing. If the decisive quote cannot be found, confidence is cut in half. A hallucinated citation can never carry a verdict.

## Pipeline

```
SEC EDGAR (original 10-K) → anonymize → sections → chunks → embeddings (FAISS)
        → screen for candidate findings → Auditor → Defender → Adjudicator
        → citation verification → signal score
```

1. **Fetch** the original 10-K from EDGAR: the version investors saw before any restatement
2. **Anonymize** company names, ticker, and executives to control for look-ahead bias
3. **Index** the filing by section into a FAISS vector store for semantic search
4. **Screen** for candidate red flags across revenue, risk factors, litigation, and related parties
5. **Cross-examine** each candidate with the three agents
6. **Verify and score** every citation and the filing as a whole

## Validation

- **Finding survival rate:** a single agent flagged [X] items; after cross-examination, [Y] survived.
- **Backtest:** Super Micro Computer's FY2016 10-K, filed about a year before its revenue recognition investigation became public, against a clean peer. Signal score: [target] vs [control].
- **Blind mode:** results with company identities masked.

## Metrics

| Metric | Meaning |
|---|---|
| Signal score (0-100) | Confidence-weighted share of severity-weighted findings that survived review |
| Citation integrity | Share of all agent quotes verified against the filing |
| Signal gap | Target signal minus control signal |

## Quickstart

Requires Python 3.10+, an Anthropic API key, and a contact email for SEC EDGAR.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add ANTHROPIC_API_KEY and SEC_EMAIL

python -m pytest -q         # offline tests, no API calls

python -m pecora.adversarial.run --ticker SMCI --year 2016 --max-findings 2
python -m pecora.adversarial.backtest --target SMCI:2016 --control NTAP:2016
streamlit run app.py
```

Results save to `outputs/adversarial/`. The app's Case files mode replays them offline.

## Project structure

```
pecora/
  ingestion/     EDGAR fetch, section detection, chunking, anonymization
  retrieval/     embeddings, FAISS store, focus-area retrieval
  screen.py      first-pass candidate finding generator
  adversarial/   agents, prompts, citation verifier, runner, backtest
app.py           Streamlit demo
tests/           offline test suite
```

## Limitations

- A handful of backtest cases is a demonstration, not statistical proof.
- Anonymization masks names, not facts; a distinctive business can still hint at identity, which is why a control company is included.
- Each finding takes three model calls, so Pecora.ai is built for focused review, not bulk screening.

## Team

Saarang Govinda Rajan, Mark Aashish Lnu · UW-Madison
