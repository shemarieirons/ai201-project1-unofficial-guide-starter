from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from textwrap import indent


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.vector_store import DEFAULT_TOP_K, query_chunks


def format_metadata(metadata: dict[str, object]) -> str:
    return json.dumps(metadata, ensure_ascii=True, indent=2, sort_keys=True)


def retrieve(question: str, top_k: int = DEFAULT_TOP_K) -> dict[str, object]:
    return query_chunks(question, top_k=top_k)


def print_results(question: str, results: dict[str, object]) -> None:
    print(f"Question: {question}")
    print()

    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not ids:
        print("No results returned.")
        return

    for rank, chunk_id in enumerate(ids, start=1):
        document = documents[rank - 1] if rank - 1 < len(documents) else ""
        metadata = metadatas[rank - 1] if rank - 1 < len(metadatas) else {}
        distance = distances[rank - 1] if rank - 1 < len(distances) else None
        similarity = 1 - distance if isinstance(distance, (int, float)) else None

        print(f"Rank {rank}")
        print(f"  chunk_id: {chunk_id}")
        if distance is not None:
            print(f"  distance: {distance:.6f}")
        if similarity is not None:
            print(f"  similarity: {similarity:.6f}")
        print(f"  source document: {metadata.get('source_file', 'unknown')}")
        print(f"  source: {metadata.get('source', 'unknown')}")
        print(f"  metadata: {format_metadata(metadata)}")
        print("  chunk text:")
        print(indent(document or "", "    "))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run semantic retrieval against the ChromaDB collection.")
    parser.add_argument("question", nargs="?", help="Question to search for")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of chunks to retrieve")
    args = parser.parse_args()

    question = args.question or input("Enter a question: ").strip()
    if not question:
        raise ValueError("A question is required.")

    results = retrieve(question, top_k=args.top_k)
    print_results(question, results)


if __name__ == "__main__":
    main()