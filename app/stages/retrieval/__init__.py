# Stage 2: Hybrid RAG — Retrieval, Re-ranking, Compression
# Public re-exports so callers use `from app.stages.retrieval import ...`
from app.stages.retrieval.rag import retrieve_context

__all__ = ["retrieve_context"]
