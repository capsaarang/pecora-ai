"""
Anonymizer: look-ahead bias control

The LLM may already know how a famous company's story ended. To show that findings come
from the filing text and not from memory, we mask the company's names, its people and its
products before any agent sees the text, then count what still leaks.

What is masked (anonymize):
  [COMPANY]    the EDGAR name, its short forms ("MiMedx" from "MIMEDX GROUP, INC."), the ticker
  [EXECUTIVE]  names on the signature page and after Mr./Ms./Dr., and their surnames alone
  [PRODUCT]    names marked with (R) or (TM), and recurring CamelCase brand words ("SolidFire")

A short form, surname or brand word is masked on its own only when it never appears in
lowercase in the filing, so ordinary words ("super", "general", "black") are left alone.
"""

import re
from collections import Counter

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
    r",?\s+(inc|incorporated|corp|corporation|co|company|ltd|llc|plc|holdings|group)\.?$",
    re.IGNORECASE,
)
_ARTICLE = re.compile(r"^the\s+", re.IGNORECASE)
_NAME_WORD = r"(?:[A-Z]\.|[A-Z][A-Za-z'-]+)"  # only a single-letter initial takes a period
_SIGNATURE = re.compile(rf"/s/\s*({_NAME_WORD}(?:[ \t]+{_NAME_WORD}){{1,3}})")
_HONORIFIC = re.compile(rf"\b(?:Mr|Ms|Mrs|Dr)\.?[ \t]+((?:{_NAME_WORD}[ \t]+){{0,2}}[A-Z][A-Za-z'-]{{2,}})")
_MARKED = re.compile(r"([A-Z][\w-]*(?:[ ][A-Z][\w-]*){0,2})[ ]?(?:®|™|\(R\)|\(TM\))")
_CAMEL = re.compile(r"(?<![\w-])([A-Z][a-z]+(?:[A-Z][a-z0-9]*)+)(?![\w-])")
_FIRMS = re.compile(r"\b(LLP|LLC|Inc|Corp|Company|Bank)\b", re.IGNORECASE)
_NOT_NAMES = {"January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December", "GmbH"}
_WEB = re.compile(r"\S+@\S+|(?:https?://|www\.)\S+|\b[\w.-]+\.(?:com|net|org|gov|edu)\b\S*", re.IGNORECASE)


def _proper_noun(word: str, text: str, min_hits: int = 1) -> bool:
    """True when `word` appears in the filing and never in all-lowercase form (web and email addresses aside)."""
    hits = re.findall(rf"(?<![\w-]){re.escape(word)}(?![\w-])", _WEB.sub(" ", text), re.IGNORECASE)
    return len(hits) >= min_hits and not any(h.islower() for h in hits)


def build_aliases(company_name: str | None = None, ticker: str | None = None,
                  extra: list[str] | None = None, text: str | None = None) -> list[str]:
    """All names to mask, longest first so full names win over fragments."""
    aliases: set[str] = set()
    if company_name:
        name = re.sub(r"\s+", " ", company_name).strip()
        aliases.add(name)
        stripped = name
        while (shorter := _SUFFIX.sub("", stripped).strip(" ,")) != stripped:  # "MIMEDX GROUP, INC." -> "MIMEDX"
            aliases.add(shorter)
            stripped = shorter
        base = _ARTICLE.sub("", stripped)
        aliases.update({base} - {""})
        words = base.split()
        if text:  # short forms the filing uses on their own: "MiMedx", "Super Micro"
            for short in {" ".join(words[:2]), words[0]} - {base}:
                if len(short) >= 4 and _proper_noun(short, text):
                    aliases.add(short)
    if ticker:
        aliases.add(ticker.upper())
        aliases.update(KNOWN_ALIASES.get(ticker.upper(), []))
    if extra:
        aliases.update(extra)
    return sorted((a for a in aliases if len(a) >= 3), key=len, reverse=True)


def people_for(ticker: str | None) -> list[str]:
    return KNOWN_PEOPLE.get((ticker or "").upper(), [])


def find_people(text: str) -> list[str]:
    """Full names from signature lines and honorifics, plus surnames that are never ordinary words."""
    names = {re.sub(r"\s+", " ", m).strip(" .") for m in _SIGNATURE.findall(text) + _HONORIFIC.findall(text)}
    names = {n for n in names if not _FIRMS.search(n) and n.split()[-1] not in _NOT_NAMES}
    surnames = {n.split()[-1] for n in names}
    surnames = {s for s in surnames if len(s) >= 3 and _proper_noun(s, text)}
    for s in surnames:  # full forms seen only in prose: "Parker H. Petit"
        names |= set(re.findall(rf"\b[A-Z][a-z]+(?:[ \t]+[A-Z]\.)?[ \t]+{re.escape(s)}\b", text))
    return sorted(names | surnames, key=len, reverse=True)


def find_products(text: str, exclude: list[str]) -> list[str]:
    """Trademark-marked names, plus CamelCase brand words used at least 3 times, never in lowercase."""
    marked = {m.strip() for m in _MARKED.findall(text) if not _ARTICLE.match(m)}
    camel = {w for w, n in Counter(_CAMEL.findall(text)).items() if n >= 3}
    skip = {e.lower() for e in exclude} | {n.lower() for n in _NOT_NAMES}
    return sorted((p for p in marked | camel if p.lower() not in skip and len(p) >= 4 and _proper_noun(p, text)),
                  key=len, reverse=True)


def _is_ticker(term: str) -> bool:
    return term.isupper() and len(term) <= 5 and " " not in term


def _mask(text: str, term: str, token: str) -> str:
    # Tickers match case-sensitively: ALL, CAT or NOW must not erase the words "all", "cat", "now".
    # Hyphens count as word characters so "Black" never touches "Black-Scholes".
    flags = 0 if _is_ticker(term) else re.IGNORECASE
    return re.sub(rf"(?<![\w-]){re.escape(term)}(?![\w-])", token, text, flags=flags)


def anonymize_text(text: str, aliases: list[str], people: list[str] | None = None,
                   mask_years: bool = False, products: list[str] | None = None) -> str:
    for a in aliases:
        text = _mask(text, a, "[COMPANY]")
    for p in people or []:
        text = _mask(text, p, "[EXECUTIVE]")
    for p in products or []:
        text = _mask(text, p, "[PRODUCT]")
    if mask_years:
        # Removes timing context too. Use only for the strict bias-control run.
        text = re.sub(r"\b(19[89]\d|20[0-2]\d)\b", "[YEAR]", text)
    return text


def anonymize(text: str, company_name: str | None = None, ticker: str | None = None,
              extra: list[str] | None = None, mask_years: bool = False) -> tuple[str, dict]:
    """Masked text and a report: what was masked, and how often each masked term still appears."""
    aliases = build_aliases(company_name, ticker, extra, text)
    people = sorted(set(people_for(ticker)) | set(find_people(text)), key=len, reverse=True)
    products = find_products(text, aliases + people)
    masked = anonymize_text(text, aliases, people, mask_years, products)
    leaks = {t: n for t in aliases + people + products
             if (n := len(re.findall(rf"(?<![\w-]){re.escape(t)}(?![\w-])", masked,
                                     0 if _is_ticker(t) else re.IGNORECASE)))}
    return masked, {"aliases": aliases, "people": people, "products": products, "leaks": leaks}
