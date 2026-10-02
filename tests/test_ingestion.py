"""
Tests for ingestion pipeline: section detection and chunking.
"""

import pytest
from pecora.ingestion.sections import detect_sections, extract_notes
from pecora.ingestion.chunker import chunk_sections


SAMPLE_10K = """
Item 1. Business

Apple Inc. designs, manufactures, and markets smartphones, personal computers,
tablets, wearables, and accessories worldwide. The Company sells its products
directly to consumers and through third-party cellular network carriers,
wholesalers, retailers, and resellers.

Item 1A. Risk Factors

The Company's business, financial condition, and operating results can be affected
by a number of factors. A majority of the Company's revenue comes from a relatively
small number of products. If demand for these products declines, the Company's
financial results could be adversely impacted.

Concentration risk: iPhone net sales represented approximately 52% of the Company's
total net sales for fiscal 2023. A decline in demand for iPhone could materially
harm the Company's financial condition.

Item 7. Management's Discussion and Analysis

Net sales for fiscal 2023 totaled $394.3 billion, compared to $394.3 billion in
fiscal 2022. Products net sales decreased 7% year-over-year. Services net sales
increased 9% year-over-year to $85.2 billion.

Item 3. Legal Proceedings

The Company is subject to legal proceedings and claims that have not been finally
adjudicated. The Company is subject to a class-action lawsuit in California
alleging violations of consumer protection laws.

NOTE 1. Summary of Significant Accounting Policies

Revenue Recognition: The Company recognizes revenue when control of the promised
products or services is transferred to customers. For products, this is generally
when the product is delivered.

NOTE 14. Related Party Transactions

Certain members of the Company's board of directors are also board members of
companies with which the Company conducts business in the ordinary course.
"""


class TestSectionDetector:
    def test_detects_multiple_sections(self):
        sections = detect_sections(SAMPLE_10K)
        assert len(sections) >= 4

    def test_section_names_populated(self):
        sections = detect_sections(SAMPLE_10K)
        names = [s.name for s in sections]
        assert any("Risk" in n for n in names)
        assert any("Business" in n or "Legal" in n or "Discussion" in n for n in names)

    def test_section_text_nonempty(self):
        sections = detect_sections(SAMPLE_10K)
        for s in sections:
            assert len(s.text) > 0

    def test_fallback_on_no_sections(self):
        sections = detect_sections("This document has no item headers.")
        assert len(sections) == 1
        assert sections[0].item_number == "N/A"

    def test_extract_notes(self):
        notes = extract_notes(SAMPLE_10K)
        assert len(notes) >= 1
        assert any(n["note_number"] == "1" for n in notes)


class TestChunker:
    def test_chunks_produced(self):
        sections = detect_sections(SAMPLE_10K)
        chunks = chunk_sections(sections, chunk_size=400, overlap=80)
        assert len(chunks) > 0

    def test_chunk_ids_unique(self):
        sections = detect_sections(SAMPLE_10K)
        chunks = chunk_sections(sections)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_text_nonempty(self):
        sections = detect_sections(SAMPLE_10K)
        chunks = chunk_sections(sections)
        for c in chunks:
            assert len(c.text.strip()) > 50

    def test_chunk_has_section_metadata(self):
        sections = detect_sections(SAMPLE_10K)
        chunks = chunk_sections(sections)
        for c in chunks:
            assert c.section_name
            assert c.item_number

    def test_small_chunk_size(self):
        sections = detect_sections(SAMPLE_10K)
        chunks = chunk_sections(sections, chunk_size=200, overlap=40)
        # Smaller chunks → more of them
        chunks_large = chunk_sections(sections, chunk_size=1200, overlap=100)
        assert len(chunks) >= len(chunks_large)
