"""
Chunker: splits 10-K sections into overlapping, paragraph-aligned passages for embedding.

Paragraphs are packed into chunks of about `chunk_size` characters. The trailing
paragraphs (up to `overlap` characters) of one chunk start the next, and paragraphs
over 1,200 characters are first split at sentence ends.
"""

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_id: str
    section_name: str
    item_number: str
    text: str

    def __repr__(self):
        preview = self.text[:60].replace("\n", " ")
        return f"Chunk({self.chunk_id}, {self.section_name}: '{preview}...')"


def chunk_sections(sections: list, chunk_size: int = 800, overlap: int = 150) -> list[Chunk]:
    return [chunk for idx, section in enumerate(sections)
            for chunk in _chunk_text(section.text, section.name, section.item_number,
                                     chunk_size, overlap, idx)]


def _chunk_text(text: str, section_name: str, item_number: str, chunk_size: int, overlap: int,
                section_idx: int = 0) -> list[Chunk]:
    # The section index keeps ids unique: a 10-K's table of contents repeats each Item header
    prefix = f"{_slugify(item_number)}-s{section_idx:02d}"
    chunks: list[Chunk] = []

    def flush(paras: list[str]) -> None:
        body = "\n\n".join(paras).strip()
        if len(body) > 50:  # skip trivially short chunks
            chunks.append(Chunk(f"{prefix}-{len(chunks):03d}", section_name, item_number, body))

    current: list[str] = []
    size = 0
    for para in _split_paragraphs(text):
        if current and size + len(para) > chunk_size:
            flush(current)
            kept: list[str] = []
            for p in reversed(current):  # carry the last paragraphs over as overlap
                if sum(map(len, kept)) + len(p) > overlap:
                    break
                kept.insert(0, p)
            current, size = kept, sum(map(len, kept))
        current.append(para)
        size += len(para)
    if current:
        flush(current)
    return chunks


def _split_paragraphs(text: str) -> list[str]:
    """Paragraphs split on blank lines; any over 1,200 characters are cut into ~900-character runs of sentences."""
    result = []
    for p in (p.strip() for p in re.split(r"\n\s*\n", text)):
        if not p:
            continue
        if len(p) <= 1200:
            result.append(p)
            continue
        run: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+", p):
            run.append(sentence)
            if sum(map(len, run)) > 900:
                result.append(" ".join(run))
                run = []
        if run:
            result.append(" ".join(run))
    return result


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "-", text.lower()).strip("-")
