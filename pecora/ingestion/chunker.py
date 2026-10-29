"""
Chunker: splits 10-K sections into overlapping, paragraph-aligned passages for embedding.

Paragraphs are packed into chunks of about `chunk_size` characters. The trailing
paragraphs (up to `overlap` characters) of one chunk start the next, and paragraphs
over 1,200 characters are first split at sentence ends.

Each chunk records the filing range it was cut from (start, end). Its text joins
paragraphs with blank lines, so it equals filing[start:end] up to whitespace.
"""

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_id: str
    section_name: str
    item_number: str
    text: str
    start: int = 0  # offsets into the full filing text
    end: int = 0

    def __repr__(self):
        preview = self.text[:60].replace("\n", " ")
        return f"Chunk({self.chunk_id}, {self.section_name}: '{preview}...')"


@dataclass
class _Para:
    text: str
    start: int  # offsets into the section text
    end: int


def chunk_sections(sections: list, chunk_size: int = 800, overlap: int = 150) -> list[Chunk]:
    return [chunk for idx, section in enumerate(sections)
            for chunk in _chunk_text(section.text, section.name, section.item_number,
                                     chunk_size, overlap, idx, getattr(section, "start_char", 0))]


def _chunk_text(text: str, section_name: str, item_number: str, chunk_size: int, overlap: int,
                section_idx: int = 0, offset: int = 0) -> list[Chunk]:
    # The section index keeps ids unique: a 10-K's table of contents repeats each Item header
    prefix = f"{_slugify(item_number)}-s{section_idx:02d}"
    chunks: list[Chunk] = []

    def flush(paras: list[_Para]) -> None:
        body = "\n\n".join(p.text for p in paras).strip()
        if len(body) > 50:  # skip trivially short chunks
            chunks.append(Chunk(f"{prefix}-{len(chunks):03d}", section_name, item_number, body,
                                offset + paras[0].start, offset + paras[-1].end))

    current: list[_Para] = []
    size = 0
    for para in _split_paragraphs(text):
        if current and size + len(para.text) > chunk_size:
            flush(current)
            kept: list[_Para] = []
            for p in reversed(current):  # carry the last paragraphs over as overlap
                if sum(len(k.text) for k in kept) + len(p.text) > overlap:
                    break
                kept.insert(0, p)
            current, size = kept, sum(len(k.text) for k in kept)
        current.append(para)
        size += len(para.text)
    if current:
        flush(current)
    return chunks


def _split_paragraphs(text: str) -> list[_Para]:
    """Paragraphs split on blank lines; any over 1,200 characters are cut into ~900-character runs of sentences."""
    result: list[_Para] = []
    cursor = 0

    def locate(piece: str) -> tuple[int, int]:
        nonlocal cursor
        start = text.index(piece, cursor)  # pieces are stripped substrings, in order
        cursor = start + len(piece)
        return start, cursor

    for p in (p.strip() for p in re.split(r"\n\s*\n", text)):
        if not p:
            continue
        if len(p) <= 1200:
            result.append(_Para(p, *locate(p)))
            continue
        run: list[str] = []
        spans: list[tuple[int, int]] = []
        for sentence in re.split(r"(?<=[.!?])\s+", p):
            run.append(sentence)
            spans.append(locate(sentence))
            if sum(map(len, run)) > 900:
                result.append(_Para(" ".join(run), spans[0][0], spans[-1][1]))
                run, spans = [], []
        if run:
            result.append(_Para(" ".join(run), spans[0][0], spans[-1][1]))
    return result


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "-", text.lower()).strip("-")
