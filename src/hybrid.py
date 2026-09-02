"""Hybrid retrieval: BM25 keyword search fused with dense semantic search.

Motivation is in planning.md under Stretch Feature Plan. The baseline system's documented
failure is lexical: a proper noun like "Blackstone" is the most discriminative token in the
query, but it is a small fraction of a chunk whose embedding is dominated by a header block
that is near-identical across all 24 review chunks. BM25 scores that surname directly.

Scores are combined by min-max normalizing each list to [0, 1] across the candidate set and
taking a weighted sum:

    hybrid = alpha * normalized_semantic + (1 - alpha) * normalized_bm25

Semantic similarity is 1 - cosine_distance so both components point the same direction
(higher is better). Normalization is required because BM25 is unbounded while cosine
similarity is bounded, so summing raw values would let BM25 dominate arbitrarily.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rank_bm25 import BM25Okapi

from src.vector_store import DEFAULT_TOP_K, get_all_chunks, query_chunks

DEFAULT_ALPHA = 0.5


@dataclass
class SearchHit:
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    score: float
    semantic_similarity: float | None = None
    bm25_score: float | None = None
    components: dict[str, float] = field(default_factory=dict)

    @property
    def source_file(self) -> str:
        return str(self.metadata.get("source_file", "unknown"))


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@lru_cache(maxsize=1)
def _load_index() -> tuple[tuple[dict[str, Any], ...], BM25Okapi]:
    corpus = tuple(get_all_chunks())
    if not corpus:
        raise ValueError("The vector store is empty. Run `python src/embed.py` first.")
    bm25 = BM25Okapi([tokenize(chunk["text"]) for chunk in corpus])
    return corpus, bm25


def matches_filter(metadata: dict[str, Any], where: dict[str, Any] | None) -> bool:
    """Equality-only metadata predicate, mirroring the ChromaDB `where` clauses used here."""
    if not where:
        return True
    for key, expected in where.items():
        actual = metadata.get(key)
        if isinstance(expected, dict):
            for operator, operand in expected.items():
                if operator == "$eq" and actual != operand:
                    return False
                if operator == "$ne" and actual == operand:
                    return False
                if operator == "$in" and actual not in operand:
                    return False
        elif actual != expected:
            return False
    return True


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    lowest, highest = min(values), max(values)
    spread = highest - lowest
    if spread <= 0:
        # Every candidate scored identically, so this retriever carries no signal.
        return {chunk_id: 0.0 for chunk_id in scores}
    return {chunk_id: (score - lowest) / spread for chunk_id, score in scores.items()}


def bm25_scores(question: str, where: dict[str, Any] | None = None) -> dict[str, float]:
    corpus, bm25 = _load_index()
    raw = bm25.get_scores(tokenize(question))
    return {
        chunk["chunk_id"]: float(raw[index])
        for index, chunk in enumerate(corpus)
        if matches_filter(chunk["metadata"], where)
    }


def semantic_scores(question: str, where: dict[str, Any] | None = None) -> dict[str, float]:
    """Similarity for every chunk. The corpus is 47 chunks, so a full ranking is cheap."""
    corpus, _ = _load_index()
    results = query_chunks(question, top_k=len(corpus), where=where)
    ids = (results.get("ids") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    return {
        chunk_id: 1.0 - float(distances[index])
        for index, chunk_id in enumerate(ids)
        if index < len(distances)
    }


def search(
    question: str,
    top_k: int = DEFAULT_TOP_K,
    method: str = "hybrid",
    alpha: float = DEFAULT_ALPHA,
    where: dict[str, Any] | None = None,
) -> list[SearchHit]:
    """Retrieve with `method` in {"semantic", "bm25", "hybrid"}."""
    if method not in {"semantic", "bm25", "hybrid"}:
        raise ValueError(f"Unknown retrieval method: {method}")

    corpus, _ = _load_index()
    chunk_by_id = {chunk["chunk_id"]: chunk for chunk in corpus}

    semantic = semantic_scores(question, where) if method in {"semantic", "hybrid"} else {}
    keyword = bm25_scores(question, where) if method in {"bm25", "hybrid"} else {}

    if method == "semantic":
        combined = dict(semantic)
    elif method == "bm25":
        combined = dict(keyword)
    else:
        normalized_semantic = normalize_scores(semantic)
        normalized_keyword = normalize_scores(keyword)
        candidate_ids = set(normalized_semantic) | set(normalized_keyword)
        combined = {
            chunk_id: alpha * normalized_semantic.get(chunk_id, 0.0)
            + (1.0 - alpha) * normalized_keyword.get(chunk_id, 0.0)
            for chunk_id in candidate_ids
        }

    ranked = sorted(combined.items(), key=lambda item: item[1], reverse=True)[:top_k]

    hits: list[SearchHit] = []
    for chunk_id, score in ranked:
        chunk = chunk_by_id.get(chunk_id, {"text": "", "metadata": {}})
        components: dict[str, float] = {}
        if method == "hybrid":
            components = {
                "normalized_semantic": normalize_scores(semantic).get(chunk_id, 0.0),
                "normalized_bm25": normalize_scores(keyword).get(chunk_id, 0.0),
            }
        hits.append(
            SearchHit(
                chunk_id=chunk_id,
                text=chunk["text"],
                metadata=chunk["metadata"],
                score=score,
                semantic_similarity=semantic.get(chunk_id),
                bm25_score=keyword.get(chunk_id),
                components=components,
            )
        )
    return hits


def hits_to_results(hits: list[SearchHit]) -> dict[str, Any]:
    """Reshape hits into the ChromaDB result dict that generate.py already consumes."""
    return {
        "ids": [[hit.chunk_id for hit in hits]],
        "documents": [[hit.text for hit in hits]],
        "metadatas": [[hit.metadata for hit in hits]],
        "distances": [
            [
                1.0 - hit.semantic_similarity if hit.semantic_similarity is not None else None
                for hit in hits
            ]
        ],
        "scores": [[hit.score for hit in hits]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run hybrid, semantic, or BM25 retrieval.")
    parser.add_argument("question", help="Question to search for")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--method", choices=["semantic", "bm25", "hybrid", "all"], default="all")
    parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    parser.add_argument("--professor", help="Filter to one professor (metadata filter)")
    parser.add_argument("--source", help="Filter to one source, e.g. 'The Hilltop'")
    args = parser.parse_args()

    where: dict[str, Any] = {}
    if args.professor:
        where["professor"] = args.professor
    if args.source:
        where["source"] = args.source

    methods = ["semantic", "bm25", "hybrid"] if args.method == "all" else [args.method]
    print(f"Question: {args.question}")
    if where:
        print(f"Metadata filter: {where}")

    for method in methods:
        print(f"\n=== {method.upper()} ===")
        for rank, hit in enumerate(search(args.question, args.top_k, method, args.alpha, where or None), start=1):
            detail = f"score={hit.score:.4f}"
            if method == "hybrid":
                detail += (
                    f" (semantic={hit.components['normalized_semantic']:.3f},"
                    f" bm25={hit.components['normalized_bm25']:.3f})"
                )
            print(f"  {rank}. {hit.chunk_id:<44} {hit.source_file:<28} {detail}")


if __name__ == "__main__":
    main()
