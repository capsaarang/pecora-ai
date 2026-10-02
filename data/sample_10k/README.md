# data/sample_10k/

Sample 10-K filings for testing Forensic-AI without requiring an EDGAR fetch.

## Included

| File | Company | Year | Source |
|---|---|---|---|
| `apple_2023_sample.txt` | Apple Inc. (AAPL) | FY2023 | Representative excerpt (not the full filing) |

## Usage

```bash
# Run audit on the included sample
python -m src.main --file data/sample_10k/apple_2023_sample.txt --ticker AAPL --year 2023

# Run with all focus areas
python -m src.main --file data/sample_10k/apple_2023_sample.txt --ticker AAPL --year 2023 --focus all
```

## Adding Real Filings

Download real 10-K filings from [SEC EDGAR](https://www.sec.gov/cgi-bin/browse-edgar) and save them here as `.txt` or `.pdf` files. The pipeline handles both formats.

Or let the pipeline fetch directly:

```bash
python -m src.main --ticker AAPL --year 2023
```
