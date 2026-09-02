from __future__ import annotations

import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingest import DATA_DIR, ingest_documents
from src.vector_store import COLLECTION_NAME, EMBEDDING_MODEL_NAME, upsert_chunks


def main() -> None:
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"Data directory not found: {DATA_DIR}")

    chunks = ingest_documents(DATA_DIR)
    collection = upsert_chunks(chunks)

    print(f"Chunks embedded: {len(chunks)}")
    print(f"Embedding model: {EMBEDDING_MODEL_NAME}")
    print(f"ChromaDB collection: {COLLECTION_NAME}")
    print(f"Stored records: {collection.count()}")


if __name__ == "__main__":
    main()