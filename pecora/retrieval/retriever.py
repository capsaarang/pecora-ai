"""
Retriever

Orchestrates RAG retrieval: embeds queries for each audit focus area,
retrieves top-k chunks from the vector store, deduplicates, and
returns a focus-area → chunks mapping for the LLM auditor.
"""

from .focus_areas import FOCUS_AREAS, get_all_queries
from .embedder import Embedder
from .vector_store import VectorStore


class Retriever:
    """
    Retrieves relevant 10-K chunks for each audit focus area.

    For each focus area:
      - Embeds all retrieval queries for that area
      - Runs similarity search in FAISS
      - Deduplicates results (same chunk may match multiple queries)
      - Returns top chunks sorted by best score

    Usage:
        retriever = Retriever(embedder, vector_store)
        context = retriever.retrieve(focus_keys=['risk_factors', 'revenue'], k=6)
        # context = {'risk_factors': [chunk, chunk, ...], 'revenue': [...]}
    """

    def __init__(self, embedder: Embedder, vector_store: VectorStore):
        self.embedder = embedder
        self.vector_store = vector_store

    def retrieve(
        self,
        focus_keys: list[str],
        k_per_query: int = 4,
        max_chunks_per_focus: int = 8,
    ) -> dict[str, list[dict]]:
        """
        Retrieve relevant chunks for all selected focus areas.

        Args:
            focus_keys: List of focus area keys (e.g. ['risk_factors', 'revenue'])
            k_per_query: Number of chunks to retrieve per individual query
            max_chunks_per_focus: Max chunks returned per focus area after dedup

        Returns:
            Dict mapping focus_key → list of {'chunk': Chunk, 'score': float}
        """
        print(f"[Retriever] Retrieving for {len(focus_keys)} focus areas...")
        result = {}

        for key in focus_keys:
            area = FOCUS_AREAS[key]
            queries = area["queries"]

            # Embed all queries for this focus area
            query_vecs = self.embedder.embed_queries(queries)

            # Batch search
            all_results = []
            for qv in query_vecs:
                all_results.append(self.vector_store.search(qv, k=k_per_query))

            # Deduplicate: keep best score per chunk_id
            seen: dict[str, dict] = {}
            for results in all_results:
                for r in results:
                    cid = r["chunk"].chunk_id
                    if cid not in seen or r["score"] > seen[cid]["score"]:
                        seen[cid] = r

            # Sort by score descending, take top N
            deduped = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
            top = deduped[:max_chunks_per_focus]

            print(f"  [{key}] {len(queries)} queries → {len(top)} unique chunks retrieved")
            result[key] = top

        return result

    def retrieve_by_query(self, query: str, k: int = 5) -> list[dict]:
        """
        Ad-hoc retrieval by a single free-text query.
        Used for agentic follow-up queries from the LLM.
        """
        vec = self.embedder.embed_query(query)
        return self.vector_store.search(vec, k=k)

    def build_context_string(
        self,
        chunks: list[dict],
        max_chars: int = 6000,
    ) -> str:
        """
        Format retrieved chunks into a context string for the LLM prompt.

        Args:
            chunks: List of retrieval results from retrieve()
            max_chars: Approximate character budget for the context

        Returns:
            Formatted multi-chunk context string
        """
        parts = []
        total_chars = 0

        for r in chunks:
            chunk = r["chunk"]
            header = f"[{chunk.item_number} — {chunk.section_name}] (relevance: {r['score']:.3f})"
            body = chunk.text.strip()
            entry = f"{header}\n{body}"

            if total_chars + len(entry) > max_chars:
                # Truncate last chunk to fit budget
                remaining = max_chars - total_chars - len(header) - 10
                if remaining > 100:
                    entry = f"{header}\n{body[:remaining]}..."
                    parts.append(entry)
                break

            parts.append(entry)
            total_chars += len(entry)

        return "\n\n---\n\n".join(parts)
