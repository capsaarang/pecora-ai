"""
FAISS Vector Store

In-memory vector index for chunk retrieval.
Stores chunk embeddings and metadata, supports top-k similarity search.
"""

import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False


class VectorStore:
    """
    FAISS-backed in-memory vector store.

    Stores dense embeddings for each chunk and supports
    top-k cosine similarity retrieval by query vector.

    Usage:
        store = VectorStore(dim=384)
        store.add(chunks, embeddings)
        results = store.search(query_vec, k=5)
    """

    def __init__(self, dim: int = 384):
        if not FAISS_AVAILABLE:
            raise ImportError("faiss-cpu is required. Run: pip install faiss-cpu")

        self.dim = dim
        # IndexFlatIP = inner product (cosine similarity when vecs are normalized)
        self.index = faiss.IndexFlatIP(dim)
        self.chunks: list = []   # parallel list to FAISS index rows
        self.total = 0

    def add(self, chunks: list, embeddings: np.ndarray) -> None:
        """
        Add chunks and their embeddings to the store.

        Args:
            chunks: List of Chunk objects
            embeddings: numpy float32 array of shape (len(chunks), dim)
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Mismatch: {len(chunks)} chunks but {len(embeddings)} embeddings"
            )
        if len(chunks) == 0:
            return

        self.index.add(embeddings)
        self.chunks.extend(chunks)
        self.total += len(chunks)
        print(f"[VectorStore] Added {len(chunks)} chunks. Total: {self.total}")

    def search(self, query_vec: np.ndarray, k: int = 5) -> list[dict]:
        """
        Retrieve top-k most similar chunks to a query vector.

        Args:
            query_vec: numpy float32 array of shape (dim,)
            k: Number of results to return

        Returns:
            List of dicts: {'chunk': Chunk, 'score': float, 'rank': int}
        """
        if self.total == 0:
            return []

        k = min(k, self.total)
        q = query_vec.reshape(1, -1).astype(np.float32)
        scores, indices = self.index.search(q, k)

        results = []
        for rank, (score, idx) in enumerate(zip(scores[0], indices[0])):
            if idx < 0:  # FAISS returns -1 for unfilled slots
                continue
            results.append({
                "chunk": self.chunks[idx],
                "score": float(score),
                "rank": rank + 1,
            })

        return results

    def search_multi(self, query_vecs: np.ndarray, k: int = 5) -> list[list[dict]]:
        """
        Run multiple queries in batch.

        Args:
            query_vecs: numpy float32 array of shape (n_queries, dim)
            k: Results per query

        Returns:
            List of result lists (one per query)
        """
        if self.total == 0:
            return [[] for _ in range(len(query_vecs))]

        k = min(k, self.total)
        q = query_vecs.astype(np.float32)
        scores, indices = self.index.search(q, k)

        all_results = []
        for row_scores, row_indices in zip(scores, indices):
            results = []
            for rank, (score, idx) in enumerate(zip(row_scores, row_indices)):
                if idx < 0:
                    continue
                results.append({
                    "chunk": self.chunks[idx],
                    "score": float(score),
                    "rank": rank + 1,
                })
            all_results.append(results)

        return all_results

    def __len__(self) -> int:
        return self.total

    def __repr__(self) -> str:
        return f"VectorStore(chunks={self.total}, dim={self.dim})"
