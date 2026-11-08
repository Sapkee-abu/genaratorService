"""Query-side embedding for ChromaDB search (change.md Blocker 1).

The real `document_chunks` collection was populated by the Import Service
using BGE-M3 (confirmed: 1024-dim, real chunks). Query vectors have to come
from the same model or similarity search is meaningless - and Chroma
rejects the wrong dimension outright (InvalidArgumentError: "expecting
embedding with dimension of 1024, got 3072" when Gemini's
gemini-embedding-001 was used instead).

Reuses the `sentence-transformers` dependency already in requirements.txt
(currently used only by common/verification.py for the semantic-similarity
gate) - no new package needed. Mirrors that module's lazy-singleton model
loading pattern.
"""

from __future__ import annotations

from sentence_transformers import SentenceTransformer

from common.config import get_settings

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        settings = get_settings()
        # Explicit CPU device: sentence-transformers otherwise auto-selects
        # CUDA when a GPU is present, but this machine's GPU (compute
        # capability 5.0) is older than what the installed PyTorch CUDA
        # build supports (>=7.5), which fails at encode() time with
        # "CUDA error: no kernel image is available for execution on the
        # device" - not a bug in the embedding logic itself.
        _model = SentenceTransformer(settings.bge_m3_model, device="cpu")
    return _model


def embed_query(text: str) -> list[float]:
    """Returns a 1024-dim query embedding, normalized (BGE-M3's own model
    card recommends normalized embeddings for dense-retrieval similarity).
    """
    model = _get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()
