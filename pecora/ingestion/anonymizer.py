"""
Anonymizer: look-ahead bias control

The LLM may already know how a famous company's story ended. To show that
findings come from the filing text and not from memory, we strip company
names, tickers, and executive names before any agent sees the text.
"""

import re

# Short names the formal EDGAR name will not catch
KNOWN_ALIASES = {
    "SMCI": ["Super Micro Computer", "Super Micro", "Supermicro"],
    "NTAP": ["NetApp"],
    "GVA": ["Granite Construction", "Granite"],
}

# Executives named in the filings. Add names as you spot them.
KNOWN_PEOPLE = {
    "SMCI": ["Charles Liang", "Howard Hideshima"],
}

_SUFFIX = re.compile(
    r",?\s+(inc|incorporated|corp|corporation|co|company|ltd|llc|plc|holdings)\.?$",
    re.IGNORECASE,
)


def build_aliases(company_name: str | None = None, ticker: str | None = None,
                  extra: list[str] | None = None) -> list[str]:
    """All names to mask, longest first so full names win over fragments."""
    aliases: set[str] = set()
    if company_name:
        name = re.sub(r"\s+", " ", company_name).strip()
        aliases.add(name)
        base = _SUFFIX.sub("", name).strip(" ,")
        if base:
            aliases.add(base)
    if ticker:
        aliases.add(ticker.upper())
        aliases.update(KNOWN_ALIASES.get(ticker.upper(), []))
    if extra:
        aliases.update(extra)
    return sorted((a for a in aliases if len(a) >= 3), key=len, reverse=True)


def people_for(ticker: str | None) -> list[str]:
    return KNOWN_PEOPLE.get((ticker or "").upper(), [])


def _mask(text: str, term: str, token: str) -> str:
    return re.sub(rf"(?<!\w){re.escape(term)}(?!\w)", token, text, flags=re.IGNORECASE)


def anonymize_text(text: str, aliases: list[str], people: list[str] | None = None,
                   mask_years: bool = False) -> str:
    for a in aliases:
        text = _mask(text, a, "[COMPANY]")
    for p in people or []:
        text = _mask(text, p, "[EXECUTIVE]")
    if mask_years:
        # Removes timing context too. Use only for the strict bias-control run.
        text = re.sub(r"\b(19[89]\d|20[0-2]\d)\b", "[YEAR]", text)
    return text
