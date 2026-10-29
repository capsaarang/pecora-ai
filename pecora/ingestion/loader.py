"""Load a 10-K from a local PDF or text file. EDGAR filings come from ingestion.edgar."""

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


def load_from_file(path: str) -> str:
    if path.lower().endswith(".pdf"):
        return _load_pdf(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _load_pdf(path: str) -> str:
    if not PDF_AVAILABLE:
        raise ImportError("pdfplumber is required for PDF loading. Run: pip install pdfplumber")
    with pdfplumber.open(path) as pdf:
        return "\n\n".join(t for page in pdf.pages if (t := page.extract_text()))
