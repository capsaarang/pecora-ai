"""
In-memory exact cosine-similarity search over chunk embeddings.

A filing has about 1,000 chunks, so a numpy matrix product is as fast as FAISS and gives
identical results to its exact IndexFlatIP. It also avoids loading FAISS's bundled libomp
next to torch's, which segfaults on macOS.
"""

import numpy as np


class VectorStore:
    def __init__(self, dim: int = 384):
        self.dim = dim
        self.vectors = np.empty((0, dim), dtype=np.float32)  # normalized, row i is chunks[i]
        self.chunks: list = []

    def add(self, chunks: list, embeddings: np.ndarray) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError(f"Mismatch: {len(chunks)} chunks but {len(embeddings)} embeddings")
        if not chunks:
            return
        self.vectors = np.vstack([self.vectors, embeddings.astype(np.float32)])
        self.chunks.extend(chunks)
        print(f"[VectorStore] Added {len(chunks)} chunks. Total: {len(self.chunks)}")

    def search(self, query_vec: np.ndarray, k: int = 5) -> list[dict]:
        """Top-k chunks for one query: [{'chunk', 'score', 'rank'}]."""
        return self.search_multi(query_vec.reshape(1, -1), k)[0]

    def search_multi(self, query_vecs: np.ndarray, k: int = 5) -> list[list[dict]]:
        """Top-k chunks for each query, highest similarity first."""
        if not self.chunks:
            return [[] for _ in range(len(query_vecs))]
        scores = query_vecs.astype(np.float32) @ self.vectors.T
        top = np.argsort(-scores, axis=1, kind="stable")[:, :k]
        return [[{"chunk": self.chunks[i], "score": float(row[i]), "rank": rank}
                 for rank, i in enumerate(idx, 1)] for row, idx in zip(scores, top)]

    def __len__(self) -> int:
        return len(self.chunks)

    def __repr__(self) -> str:
        return f"VectorStore(chunks={len(self.chunks)}, dim={self.dim})"
