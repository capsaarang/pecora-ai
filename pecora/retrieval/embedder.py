"""
Embedder: sentence-transformers vectors for chunks and queries.

Model: paraphrase-MiniLM-L3-v2 (384 dimensions, 128-token window). Vectors are
normalized, so inner product in the vector store is cosine similarity.
"""

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_MODEL = "paraphrase-MiniLM-L3-v2"


class Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        print(f"[Embedder] Loading model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_embedding_dimension()

    def embed_chunks(self, texts: list[str], batch_size: int = 16, show_progress: bool = True) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)
        vecs = self.model.encode(texts, batch_size=batch_size, show_progress_bar=show_progress,
                                 normalize_embeddings=True)
        return vecs.astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed_chunks([query], show_progress=False)[0]

    def embed_queries(self, queries: list[str]) -> np.ndarray:
        return self.embed_chunks(queries, show_progress=False)


@lru_cache(maxsize=2)
def get_embedder(model_name: str = DEFAULT_MODEL) -> Embedder:
    """One loaded model per process, shared across the filings of a backtest."""
    return Embedder(model_name)
