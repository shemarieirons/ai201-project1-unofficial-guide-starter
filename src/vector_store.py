from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer


ROOT_DIR = Path(__file__).resolve().parents[1]
CHROMA_DIR = ROOT_DIR / ".chroma"
COLLECTION_NAME = "howard_course_professor_guide"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_TOP_K = 5


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def get_collection() -> chromadb.Collection:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return embeddings.tolist()


def upsert_chunks(chunks: list[dict[str, Any]]) -> chromadb.Collection:
    collection = get_collection()
    ids = [chunk["id"] for chunk in chunks]
    documents = [chunk["text"] for chunk in chunks]
    metadatas = [dict(chunk["metadata"]) for chunk in chunks]
    embeddings = embed_texts(documents)

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )
    return collection


def query_chunks(
    question: str,
    top_k: int = DEFAULT_TOP_K,
    where: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Semantic search. `where` is passed to ChromaDB's native metadata filtering."""
    collection = get_collection()
    question_embedding = embed_texts([question])[0]
    query_kwargs: dict[str, Any] = {
        "query_embeddings": [question_embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        query_kwargs["where"] = where
    return collection.query(**query_kwargs)


def get_all_chunks() -> list[dict[str, Any]]:
    """Return every stored chunk. Used to build the BM25 index over the same corpus."""
    collection = get_collection()
    stored = collection.get(include=["documents", "metadatas"])
    ids = stored.get("ids") or []
    documents = stored.get("documents") or []
    metadatas = stored.get("metadatas") or []

    chunks: list[dict[str, Any]] = []
    for index, chunk_id in enumerate(ids):
        chunks.append(
            {
                "chunk_id": chunk_id,
                "text": documents[index] if index < len(documents) else "",
                "metadata": dict(metadatas[index]) if index < len(metadatas) else {},
            }
        )
    return chunks