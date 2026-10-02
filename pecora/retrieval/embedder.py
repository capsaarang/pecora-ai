"""
Embedder

Wraps sentence-transformers to produce dense vector embeddings
for both document chunks and retrieval queries.

Model: all-MiniLM-L6-v2
  - 384 dimensions
  - Fast inference, good semantic quality for financial text
  - ~80MB download on first use
"""

import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_MODEL = "paraphrase-MiniLM-L3-v2"

class Embedder:
    def __init__(self, model_name=DEFAULT_MODEL):
        print(f"[Embedder] Loading model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()
        print(f"[Embedder] Ready — dim: {self.dim}")

    def embed_chunks(self, texts, batch_size=16, show_progress=True):
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)
        vecs = self.model.encode(texts, batch_size=batch_size, show_progress_bar=show_progress, normalize_embeddings=True)
        return vecs.astype(np.float32)

    def embed_query(self, query):
        vec = self.model.encode([query], show_progress_bar=False, normalize_embeddings=True)
        return vec[0].astype(np.float32)

    def embed_queries(self, queries):
        return self.embed_chunks(queries, show_progress=False)
