"""
10-K Document Loader

Supports:
  1. Local PDF files (via pdfplumber)
  2. Local plain-text files
  3. SEC EDGAR (via ingestion.edgar)
"""


try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


def load_from_file(path: str) -> str:
    """
    Load a 10-K document from a local file (PDF or text).

    Args:
        path: Path to .pdf or .txt file

    Returns:
        Raw text content of the filing
    """
    if path.lower().endswith(".pdf"):
        return _load_pdf(path)
    else:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


def load_from_edgar(ticker: str, year: int) -> str:
    """
    Fetch the original 10-K for a ticker and fiscal year from SEC EDGAR.

    Delegates to ingestion.edgar, which handles paginated filing history,
    June fiscal years, and clean HTML parsing. Requires SEC_EMAIL.
    """
    from .edgar import fetch_10k
    return fetch_10k(ticker, year)["text"]


def _load_pdf(path: str) -> str:
    """Extract text from a PDF using pdfplumber."""
    if not PDF_AVAILABLE:
        raise ImportError("pdfplumber is required for PDF loading. Run: pip install pdfplumber")

    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    return "\n\n".join(text_parts)
