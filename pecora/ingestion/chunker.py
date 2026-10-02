"""
Semantic Chunker

Splits 10-K sections into overlapping chunks suitable for embedding
and retrieval. Uses paragraph-aware splitting to avoid cutting mid-sentence.
"""

import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    chunk_id: str
    section_name: str
    item_number: str
    text: str
    char_start: int
    char_end: int
    metadata: dict = field(default_factory=dict)

    def __repr__(self):
        preview = self.text[:60].replace("\n", " ")
        return f"Chunk({self.chunk_id}, {self.section_name}: '{preview}...')"


def chunk_sections(
    sections: list,
    chunk_size: int = 800,
    overlap: int = 150,
) -> list[Chunk]:
    """
    Chunk all sections into overlapping text windows.

    Args:
        sections: List of Section objects from section_detector
        chunk_size: Target characters per chunk
        overlap: Character overlap between consecutive chunks

    Returns:
        List of Chunk objects ready for embedding
    """
    all_chunks = []

    for section in sections:
        section_chunks = _chunk_text(
            text=section.text,
            section_name=section.name,
            item_number=section.item_number,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        all_chunks.extend(section_chunks)

    return all_chunks


def _chunk_text(
    text: str,
    section_name: str,
    item_number: str,
    chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    """Split a single section's text into overlapping chunks."""
    # Split into paragraphs first (respects natural boundaries)
    paragraphs = _split_paragraphs(text)

    chunks = []
    current_chars = []
    current_len = 0
    char_cursor = 0
    chunk_idx = 0

    for para in paragraphs:
        para_len = len(para)

        # If adding this paragraph exceeds chunk_size, flush current buffer
        if current_len + para_len > chunk_size and current_chars:
            chunk_text = "\n\n".join(current_chars).strip()
            if len(chunk_text) > 50:  # skip trivially short chunks
                chunk_id = f"{_slugify(item_number)}-{chunk_idx:03d}"
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    section_name=section_name,
                    item_number=item_number,
                    text=chunk_text,
                    char_start=char_cursor - current_len,
                    char_end=char_cursor,
                    metadata={"section": section_name, "item": item_number},
                ))
                chunk_idx += 1

            # Keep overlap: retain last paragraph(s) up to `overlap` chars
            overlap_paras = []
            overlap_len = 0
            for p in reversed(current_chars):
                if overlap_len + len(p) <= overlap:
                    overlap_paras.insert(0, p)
                    overlap_len += len(p)
                else:
                    break
            current_chars = overlap_paras
            current_len = overlap_len

        current_chars.append(para)
        current_len += para_len
        char_cursor += para_len

    # Flush remaining
    if current_chars:
        chunk_text = "\n\n".join(current_chars).strip()
        if len(chunk_text) > 50:
            chunk_id = f"{_slugify(item_number)}-{chunk_idx:03d}"
            chunks.append(Chunk(
                chunk_id=chunk_id,
                section_name=section_name,
                item_number=item_number,
                text=chunk_text,
                char_start=char_cursor - current_len,
                char_end=char_cursor,
                metadata={"section": section_name, "item": item_number},
            ))

    return chunks


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs by blank lines."""
    paragraphs = re.split(r"\n\s*\n", text)
    result = []
    for p in paragraphs:
        p = p.strip()
        if p:
            # Further split very long paragraphs at sentence boundaries
            if len(p) > 1200:
                sentences = re.split(r"(?<=[.!?])\s+", p)
                current = []
                current_len = 0
                for s in sentences:
                    current.append(s)
                    current_len += len(s)
                    if current_len > 900:
                        result.append(" ".join(current))
                        current = []
                        current_len = 0
                if current:
                    result.append(" ".join(current))
            else:
                result.append(p)
    return result


def _slugify(text: str) -> str:
    """Convert item number to a safe ID string."""
    return re.sub(r"[^a-z0-9]", "-", text.lower()).strip("-")
