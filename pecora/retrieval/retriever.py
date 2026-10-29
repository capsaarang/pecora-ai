"""
Retriever: the filing passages most relevant to each audit focus area.

Every query of a focus area is searched in one batched index call; a chunk matched by
several queries keeps its best score, and the top chunks by score are returned.
"""

from .embedder import Embedder
from .focus_areas import FOCUS_AREAS
from .vector_store import VectorStore


class Retriever:
    def __init__(self, embedder: Embedder, vector_store: VectorStore):
        self.embedder = embedder
        self.vector_store = vector_store

    def retrieve(self, focus_keys: list[str], k_per_query: int = 4,
                 max_chunks_per_focus: int = 8) -> dict[str, list[dict]]:
        """{focus_key: [{'chunk', 'score', 'rank'}]}, best-scoring unique chunks first."""
        print(f"[Retriever] Retrieving for {len(focus_keys)} focus areas...")
        result = {}
        for key in focus_keys:
            queries = FOCUS_AREAS[key]["queries"]
            best: dict[str, dict] = {}
            for hits in self.vector_store.search_multi(self.embedder.embed_queries(queries), k_per_query):
                for r in hits:
                    cid = r["chunk"].chunk_id
                    if cid not in best or r["score"] > best[cid]["score"]:
                        best[cid] = r
            result[key] = sorted(best.values(), key=lambda r: r["score"], reverse=True)[:max_chunks_per_focus]
            print(f"  [{key}] {len(queries)} queries → {len(result[key])} unique chunks retrieved")
        return result

    def retrieve_by_query(self, query: str, k: int = 5) -> list[dict]:
        """Free-text search, used for evidence gathering and the screener's follow-up requests."""
        return self.vector_store.search(self.embedder.embed_query(query), k=k)
