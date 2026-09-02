"""Stretch feature 2 — compare the structure-aware chunker against a naive fixed-size one.

Strategy A: the production chunker in src/ingest.py — one review per chunk, one directory
entry per chunk, 300-token paragraph groups for articles, with a professor/source header
re-attached to every chunk.

Strategy B: a naive fixed-size splitter — 1000 characters with 150 characters of overlap,
respecting no document structure at all.

Both are embedded with the same model and queried with the same 5 questions, so chunking is
the only variable. Strategy B lives in its own ChromaDB collection so the live index is
untouched. Retrieval only, so this needs no API key.

    python compare_chunking.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import chromadb

from src.eval_questions import EVAL_QUESTIONS, precision_at_k
from src.ingest import DATA_DIR
from src.vector_store import CHROMA_DIR, DEFAULT_TOP_K, embed_texts, get_collection, query_chunks

FIXED_COLLECTION_NAME = "howard_fixed_size_chunks"
FIXED_CHUNK_CHARS = 1000
FIXED_OVERLAP_CHARS = 150


def build_fixed_size_chunks() -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for path in sorted(DATA_DIR.glob("*.txt")):
        text = re.sub(r"[ \t]+", " ", path.read_text(encoding="utf-8")).strip()
        start = 0
        index = 0
        while start < len(text):
            window = text[start : start + FIXED_CHUNK_CHARS].strip()
            if window:
                index += 1
                chunks.append(
                    {
                        "id": f"{path.stem}::fixed_{index}",
                        "text": window,
                        "metadata": {"source_file": path.name, "strategy": "fixed_1000_150"},
                    }
                )
            step = FIXED_CHUNK_CHARS - FIXED_OVERLAP_CHARS
            start += step
    return chunks


def build_fixed_collection(chunks: list[dict[str, Any]]) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(FIXED_COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        name=FIXED_COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )
    collection.upsert(
        ids=[chunk["id"] for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        metadatas=[chunk["metadata"] for chunk in chunks],
        embeddings=embed_texts([chunk["text"] for chunk in chunks]),
    )
    return collection


def query_fixed(collection: chromadb.Collection, question: str, top_k: int) -> list[dict[str, Any]]:
    results = collection.query(
        query_embeddings=[embed_texts([question])[0]],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    ids = (results.get("ids") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    return [
        {
            "chunk_id": chunk_id,
            "source_file": (metadatas[index] or {}).get("source_file", "unknown"),
            "distance": distances[index],
        }
        for index, chunk_id in enumerate(ids)
    ]


def query_structure_aware(question: str, top_k: int) -> list[dict[str, Any]]:
    results = query_chunks(question, top_k=top_k)
    ids = (results.get("ids") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    return [
        {
            "chunk_id": chunk_id,
            "source_file": (metadatas[index] or {}).get("source_file", "unknown"),
            "distance": distances[index],
        }
        for index, chunk_id in enumerate(ids)
    ]


def self_containment_report(fixed_chunks: list[dict[str, Any]]) -> dict[str, int]:
    """How many fixed-size chunks are interpretable on their own?

    A review chunk is only answerable if the reader can tell which professor it is about.
    The structure-aware chunker guarantees this by construction; the fixed-size one does not.
    """
    review_chunks = [c for c in fixed_chunks if c["metadata"]["source_file"].startswith("professor_")]
    missing_professor = [c for c in review_chunks if not re.search(r"^Professor:", c["text"], re.M)]
    spans_multiple_reviews = [c for c in review_chunks if len(re.findall(r"(?m)^Review\s+\d+", c["text"])) > 1]
    split_mid_review = [
        c
        for c in review_chunks
        if re.search(r"(?m)^Review\s+\d+", c["text"]) and not c["text"].rstrip().endswith(".")
    ]
    return {
        "review_chunks": len(review_chunks),
        "missing_professor_name": len(missing_professor),
        "spans_multiple_reviews": len(spans_multiple_reviews),
        "ends_mid_sentence": len(split_mid_review),
    }


def main() -> None:
    fixed_chunks = build_fixed_size_chunks()
    print(f"Strategy A (structure-aware): {get_collection().count()} chunks")
    print(f"Strategy B (fixed 1000/150):  {len(fixed_chunks)} chunks")
    fixed_collection = build_fixed_collection(fixed_chunks)

    containment = self_containment_report(fixed_chunks)

    lines: list[str] = [
        "# Chunking Strategy Comparison",
        "",
        "Generated by `python compare_chunking.py`.",
        "",
        "| | Strategy A — structure-aware | Strategy B — fixed size |",
        "|---|---|---|",
        "| Rule | one review / one directory entry per chunk; 300-token paragraph groups for articles | 1000 characters, 150-character overlap, structure ignored |",
        f"| Chunk count | {get_collection().count()} | {len(fixed_chunks)} |",
        "| Professor header re-attached | yes, every chunk | no |",
        "",
        "Both strategies use `all-MiniLM-L6-v2` and cosine distance, and are queried with the",
        "same 5 evaluation questions, so chunking is the only variable. Retrieval is",
        "semantic-only on both sides so the hybrid stretch feature does not confound the result.",
        "",
    ]

    totals: dict[str, list[float]] = {"A": [], "B": []}

    for item in EVAL_QUESTIONS:
        hits_a = query_structure_aware(item.question, DEFAULT_TOP_K)
        hits_b = query_fixed(fixed_collection, item.question, DEFAULT_TOP_K)
        precision_a = precision_at_k([h["source_file"] for h in hits_a], item.relevant_sources)
        precision_b = precision_at_k([h["source_file"] for h in hits_b], item.relevant_sources)
        if precision_a is not None:
            totals["A"].append(precision_a)
        if precision_b is not None:
            totals["B"].append(precision_b)

        lines.append(f"## Question {item.number}")
        lines.append("")
        lines.append(f"`{item.question}`")
        lines.append("")
        lines.append("| Rank | A: chunk | A: distance | B: chunk | B: distance |")
        lines.append("|---|---|---|---|---|")
        for rank in range(DEFAULT_TOP_K):
            a = hits_a[rank] if rank < len(hits_a) else None
            b = hits_b[rank] if rank < len(hits_b) else None
            a_cells = f"`{a['chunk_id']}` | {a['distance']:.4f}" if a else "— | —"
            b_cells = f"`{b['chunk_id']}` | {b['distance']:.4f}" if b else "— | —"
            lines.append(f"| {rank + 1} | {a_cells} | {b_cells} |")
        lines.append("")
        lines.append(
            f"precision@5 — **A: {'n/a' if precision_a is None else f'{precision_a:.2f}'}**, "
            f"**B: {'n/a' if precision_b is None else f'{precision_b:.2f}'}**"
        )
        lines.append("")

    mean_a = sum(totals["A"]) / len(totals["A"]) if totals["A"] else 0.0
    mean_b = sum(totals["B"]) / len(totals["B"]) if totals["B"] else 0.0

    lines.append("## Result")
    lines.append("")
    lines.append("| Strategy | Mean precision@5 (4 in-scope questions) |")
    lines.append("|---|---|")
    lines.append(f"| A — structure-aware | {mean_a:.3f} |")
    lines.append(f"| B — fixed 1000/150 | {mean_b:.3f} |")
    lines.append("")
    lines.append("## Chunk self-containment (Strategy B)")
    lines.append("")
    lines.append("Precision alone understates the difference, because a chunk can come from the")
    lines.append("right file and still be unusable. Of Strategy B's review chunks:")
    lines.append("")
    lines.append("| Property | Count |")
    lines.append("|---|---|")
    lines.append(f"| Review chunks total | {containment['review_chunks']} |")
    lines.append(f"| Missing the `Professor:` header (reader cannot tell who it is about) | {containment['missing_professor_name']} |")
    lines.append(f"| Contain more than one review (opinions blended) | {containment['spans_multiple_reviews']} |")
    lines.append(f"| End mid-sentence | {containment['ends_mid_sentence']} |")
    lines.append("")

    output_path = ROOT_DIR / "stretch_chunking_results.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nMean precision@5 — A: {mean_a:.3f}  B: {mean_b:.3f}")
    print(f"Self-containment (B): {containment}")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
