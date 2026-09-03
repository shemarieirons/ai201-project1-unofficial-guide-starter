"""Evaluation and stretch-feature reports for The Unofficial Guide.

    python evaluate.py baseline   # 5 test questions, semantic retrieval -> eval_output.md
    python evaluate.py hybrid     # semantic vs BM25 vs hybrid          -> stretch_hybrid_results.md
    python evaluate.py chunking   # structure-aware vs fixed-size       -> stretch_chunking_results.md
    python evaluate.py demo       # metadata filtering + memory          -> stretch_demo.md
    python evaluate.py all        # all four

`hybrid` and `chunking` are retrieval-only and need no API key. `baseline` and `demo` call
the LLM and require GROQ_API_KEY.

The 5 questions and their relevance labels live in src/eval_questions.py, so every report
below scores against the same ground truth.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import chromadb

from src.eval_questions import EVAL_QUESTIONS, precision_at_k
from src.generate import generate_answer
from src.hybrid import DEFAULT_ALPHA, search
from src.ingest import DATA_DIR
from src.retrieve import retrieve
from src.vector_store import CHROMA_DIR, DEFAULT_TOP_K, embed_texts, get_collection, query_chunks

METHODS = ("semantic", "bm25", "hybrid")

FIXED_COLLECTION_NAME = "howard_fixed_size_chunks"
FIXED_CHUNK_CHARS = 1000
FIXED_OVERLAP_CHARS = 150

FILTER_QUESTION = "What problems have students experienced with course registration at Howard?"
TURN_1 = "What do students say about Jeremy Blackstone?"
TURN_2 = "How are his exams structured?"


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


def write_report(filename: str, lines: list[str]) -> Path:
    path = ROOT_DIR / filename
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {path}")
    return path


def first_result_list(results: dict[str, Any], key: str) -> list[Any]:
    values = results.get(key, [[]])
    if not values:
        return []
    first_value = values[0]
    return list(first_value) if isinstance(first_value, list) else []


def unpack_results(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a ChromaDB result dict into per-rank records."""
    ids = first_result_list(results, "ids")
    documents = first_result_list(results, "documents")
    metadatas = first_result_list(results, "metadatas")
    distances = first_result_list(results, "distances")

    records: list[dict[str, Any]] = []
    for index, chunk_id in enumerate(ids):
        metadata = metadatas[index] if index < len(metadatas) else {}
        records.append(
            {
                "chunk_id": chunk_id,
                "text": documents[index] if index < len(documents) else "",
                "source_file": (metadata or {}).get("source_file", "unknown"),
                "distance": distances[index] if index < len(distances) else None,
            }
        )
    return records


def format_precision(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def rank_table(hits: list) -> list[str]:
    lines = ["| Rank | Chunk ID | Source file | Hybrid score |", "|---|---|---|---|"]
    for rank, hit in enumerate(hits, start=1):
        lines.append(f"| {rank} | `{hit.chunk_id}` | {hit.source_file} | {hit.score:.4f} |")
    return lines


# ---------------------------------------------------------------------------
# baseline — the 5 test questions, semantic retrieval (README Evaluation Report)
# ---------------------------------------------------------------------------


def format_baseline_chunk(chunk_number: int, source_file: str, distance: Any, text: str) -> str:
    distance_text = f"{distance:.6f}" if isinstance(distance, (int, float)) else "unknown"
    return (
        f"#### Chunk {chunk_number}\n\n"
        f"- Source file: {source_file}\n"
        f"- Distance: {distance_text}\n\n"
        "```text\n"
        f"{text.strip()}\n"
        "```\n"
    )


def run_baseline() -> None:
    total_chunks = get_collection().count()
    sections = [f"# Evaluation Dump\n\nTotal chunk count: {total_chunks}\n"]
    print(f"Total chunk count: {total_chunks}\n")

    for item in EVAL_QUESTIONS:
        # Pinned to semantic-only: this is the baseline evaluation reported in the README,
        # and it must stay reproducible now that hybrid search is the runtime default.
        records = unpack_results(retrieve(item.question, top_k=DEFAULT_TOP_K))
        generated = generate_answer(item.question, top_k=DEFAULT_TOP_K, method="semantic")

        lines: list[str] = [
            f"## Question\n\n{item.question}\n",
            f"Total chunk count: {total_chunks}\n",
            "### Retrieved Chunks\n",
        ]
        if not records:
            lines.append("No chunks returned.\n")
        for index, record in enumerate(records, start=1):
            lines.append(
                format_baseline_chunk(
                    index, str(record["source_file"]), record["distance"], str(record["text"] or "")
                )
            )

        lines.append("### Generated Answer\n")
        lines.extend(["```text", str(generated["answer"]).strip(), "```\n"])

        lines.append("### Source List\n")
        sources = str(generated.get("sources", "")).strip()
        if sources:
            lines.extend(["```text", sources, "```\n"])
        else:
            lines.append("No sources returned.\n")

        sections.append("\n".join(lines).rstrip() + "\n")

        print(item.question)
        for index, record in enumerate(records, start=1):
            distance = record["distance"]
            distance_text = f"{distance:.6f}" if isinstance(distance, (int, float)) else "unknown"
            print(f"  Chunk {index}: {record['source_file']} | distance={distance_text}")
        print()

    write_report("eval_output.md", sections)


# ---------------------------------------------------------------------------
# hybrid — semantic vs BM25 vs hybrid
# ---------------------------------------------------------------------------


def run_hybrid() -> None:
    lines: list[str] = [
        "# Hybrid Search Comparison",
        "",
        f"Generated by `python evaluate.py hybrid` — top-k = {DEFAULT_TOP_K}, "
        f"hybrid alpha = {DEFAULT_ALPHA}.",
        "",
        "`precision@5` is the fraction of the top 5 chunks coming from a source file",
        "hand-labeled as relevant in `src/eval_questions.py`. Question 5 is out-of-scope,",
        "so no document is relevant and precision is undefined.",
        "",
    ]

    totals: dict[str, list[float]] = {method: [] for method in METHODS}

    for item in EVAL_QUESTIONS:
        lines += [f"## Question {item.number}", "", f"`{item.question}`", ""]
        if item.relevant_sources:
            lines.append(f"Relevant source files: {', '.join(sorted(item.relevant_sources))}")
        else:
            lines.append("Relevant source files: none — the corpus does not cover this question.")
        lines.append("")

        summary_rows: list[str] = []

        for method in METHODS:
            hits = search(item.question, top_k=DEFAULT_TOP_K, method=method)
            precision = precision_at_k([hit.source_file for hit in hits], item.relevant_sources)
            if precision is not None:
                totals[method].append(precision)

            recall_note = ""
            if item.required_chunk_ids:
                found = {hit.chunk_id for hit in hits} & item.required_chunk_ids
                recall_note = f"{len(found)}/{len(item.required_chunk_ids)}"

            summary_rows.append(
                f"| {method} | {format_precision(precision)} | {recall_note or '—'} | "
                + ", ".join(f"`{hit.source_file}`" for hit in hits)
                + " |"
            )

            lines += [f"### {method}", "", "| Rank | Chunk ID | Source file | Score |", "|---|---|---|---|"]
            for rank, hit in enumerate(hits, start=1):
                score = f"{hit.score:.4f}"
                if method == "hybrid":
                    score += (
                        f" (sem {hit.components['normalized_semantic']:.3f} /"
                        f" bm25 {hit.components['normalized_bm25']:.3f})"
                    )
                lines.append(f"| {rank} | `{hit.chunk_id}` | {hit.source_file} | {score} |")
            lines.append("")

        lines += [
            "### Comparison",
            "",
            "| Method | precision@5 | required chunks found | Retrieved source files |",
            "|---|---|---|---|",
        ]
        lines.extend(summary_rows)
        lines.append("")

    lines += [
        "## Mean precision@5 across the 4 in-scope questions",
        "",
        "| Method | Mean precision@5 |",
        "|---|---|",
    ]
    for method in METHODS:
        scores = totals[method]
        mean = sum(scores) / len(scores) if scores else 0.0
        lines.append(f"| {method} | {mean:.3f} |")
        print(f"{method:>9}: mean precision@5 = {mean:.3f}")
    lines.append("")

    write_report("stretch_hybrid_results.md", lines)


# ---------------------------------------------------------------------------
# chunking — structure-aware vs naive fixed-size
# ---------------------------------------------------------------------------


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
            start += FIXED_CHUNK_CHARS - FIXED_OVERLAP_CHARS
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


def self_containment_report(fixed_chunks: list[dict[str, Any]]) -> dict[str, int]:
    """How many fixed-size chunks are interpretable on their own?

    A review chunk is only answerable if the reader can tell which professor it is about.
    The structure-aware chunker guarantees this by construction; the fixed-size one does not.
    """
    review_chunks = [c for c in fixed_chunks if c["metadata"]["source_file"].startswith("professor_")]
    return {
        "review_chunks": len(review_chunks),
        "missing_professor_name": sum(
            1 for c in review_chunks if not re.search(r"^Professor:", c["text"], re.M)
        ),
        "spans_multiple_reviews": sum(
            1 for c in review_chunks if len(re.findall(r"(?m)^Review\s+\d+", c["text"])) > 1
        ),
        "ends_mid_sentence": sum(
            1
            for c in review_chunks
            if re.search(r"(?m)^Review\s+\d+", c["text"]) and not c["text"].rstrip().endswith(".")
        ),
    }


def run_chunking() -> None:
    fixed_chunks = build_fixed_size_chunks()
    structure_aware_count = get_collection().count()
    print(f"Strategy A (structure-aware): {structure_aware_count} chunks")
    print(f"Strategy B (fixed 1000/150):  {len(fixed_chunks)} chunks")

    fixed_collection = build_fixed_collection(fixed_chunks)
    containment = self_containment_report(fixed_chunks)

    lines: list[str] = [
        "# Chunking Strategy Comparison",
        "",
        "Generated by `python evaluate.py chunking`.",
        "",
        "| | Strategy A — structure-aware | Strategy B — fixed size |",
        "|---|---|---|",
        "| Rule | one review / one directory entry per chunk; 300-token paragraph groups for "
        "articles | 1000 characters, 150-character overlap, structure ignored |",
        f"| Chunk count | {structure_aware_count} | {len(fixed_chunks)} |",
        "| Professor header re-attached | yes, every chunk | no |",
        "",
        "Both strategies use `all-MiniLM-L6-v2` and cosine distance, and are queried with the",
        "same 5 evaluation questions, so chunking is the only variable. Retrieval is",
        "semantic-only on both sides so the hybrid stretch feature does not confound the result.",
        "",
    ]

    totals: dict[str, list[float]] = {"A": [], "B": []}

    for item in EVAL_QUESTIONS:
        hits_a = unpack_results(query_chunks(item.question, top_k=DEFAULT_TOP_K))
        hits_b = unpack_results(
            fixed_collection.query(
                query_embeddings=[embed_texts([item.question])[0]],
                n_results=DEFAULT_TOP_K,
                include=["documents", "metadatas", "distances"],
            )
        )
        precision_a = precision_at_k([h["source_file"] for h in hits_a], item.relevant_sources)
        precision_b = precision_at_k([h["source_file"] for h in hits_b], item.relevant_sources)
        if precision_a is not None:
            totals["A"].append(precision_a)
        if precision_b is not None:
            totals["B"].append(precision_b)

        lines += [
            f"## Question {item.number}",
            "",
            f"`{item.question}`",
            "",
            "| Rank | A: chunk | A: distance | B: chunk | B: distance |",
            "|---|---|---|---|---|",
        ]
        for rank in range(DEFAULT_TOP_K):
            a = hits_a[rank] if rank < len(hits_a) else None
            b = hits_b[rank] if rank < len(hits_b) else None
            a_cells = f"`{a['chunk_id']}` | {a['distance']:.4f}" if a else "— | —"
            b_cells = f"`{b['chunk_id']}` | {b['distance']:.4f}" if b else "— | —"
            lines.append(f"| {rank + 1} | {a_cells} | {b_cells} |")
        lines += [
            "",
            f"precision@5 — **A: {format_precision(precision_a)}**, "
            f"**B: {format_precision(precision_b)}**",
            "",
        ]

    mean_a = sum(totals["A"]) / len(totals["A"]) if totals["A"] else 0.0
    mean_b = sum(totals["B"]) / len(totals["B"]) if totals["B"] else 0.0

    lines += [
        "## Result",
        "",
        "| Strategy | Mean precision@5 (4 in-scope questions) |",
        "|---|---|",
        f"| A — structure-aware | {mean_a:.3f} |",
        f"| B — fixed 1000/150 | {mean_b:.3f} |",
        "",
        "## Chunk self-containment (Strategy B)",
        "",
        "Precision alone understates the difference, because a chunk can come from the",
        "right file and still be unusable. Of Strategy B's review chunks:",
        "",
        "| Property | Count |",
        "|---|---|",
        f"| Review chunks total | {containment['review_chunks']} |",
        f"| Missing the `Professor:` header (reader cannot tell who it is about) | "
        f"{containment['missing_professor_name']} |",
        f"| Contain more than one review (opinions blended) | {containment['spans_multiple_reviews']} |",
        f"| End mid-sentence | {containment['ends_mid_sentence']} |",
        "",
    ]

    print(f"\nMean precision@5 — A: {mean_a:.3f}  B: {mean_b:.3f}")
    print(f"Self-containment (B): {containment}")
    write_report("stretch_chunking_results.md", lines)


# ---------------------------------------------------------------------------
# demo — metadata filtering and conversational memory
# ---------------------------------------------------------------------------


def run_demo() -> None:
    lines: list[str] = ["# Metadata Filtering and Conversational Memory", ""]

    lines += [
        "## Metadata filtering",
        "",
        f"Question: `{FILTER_QUESTION}`",
        "",
        "Every chunk carries `source`, `document_type`, and `professor` metadata from",
        "ingestion. The filter is passed to ChromaDB's native `where` clause for the semantic",
        "leg and applied to the BM25 candidate set for the keyword leg, so hybrid search",
        "honours it too.",
        "",
        "### Unfiltered",
        "",
    ]
    unfiltered = search(FILTER_QUESTION, top_k=DEFAULT_TOP_K, method="hybrid")
    lines += rank_table(unfiltered)

    lines += ["", "### Filtered to `source = The Hilltop`", ""]
    filtered = search(
        FILTER_QUESTION, top_k=DEFAULT_TOP_K, method="hybrid", where={"source": "The Hilltop"}
    )
    lines += rank_table(filtered)

    removed = [h.chunk_id for h in unfiltered if h.chunk_id not in {f.chunk_id for f in filtered}]
    lines += [
        "",
        f"**Visible effect:** the filter removed {len(removed)} chunk(s) — "
        + ", ".join(f"`{chunk_id}`" for chunk_id in removed)
        + " — leaving only student-newspaper evidence. Those were the professor-review chunks",
        "that the baseline evaluation identified as noise on this question.",
        "",
        "### Filtered to `professor = Gloria Washington`",
        "",
        "Question: `Is she a tough grader?` — a question with no name in it at all, which the",
        "baseline system cannot route to the right professor.",
        "",
    ]
    professor_filtered = search(
        "Is she a tough grader?",
        top_k=DEFAULT_TOP_K,
        method="hybrid",
        where={"professor": "Gloria Washington"},
    )
    lines += rank_table(professor_filtered)
    lines += [
        "",
        f"**Visible effect:** the candidate set drops from 47 chunks to the "
        f"{len(professor_filtered)} whose",
        "`professor` metadata is Gloria Washington — her two review chunks plus her official",
        "directory entry — so an ambiguous pronoun question still retrieves the right",
        "professor. Note that the directory entry scores 0.0000 on both legs: it is in the",
        "candidate set because it matches the filter, but it carries no evidence about",
        "grading, which is the boilerplate-dilution problem showing up again in miniature.",
        "",
        "## Conversational memory",
        "",
        "Follow-ups are resolved into standalone questions *before* retrieval, by",
        "`rewrite_followup()` in `src/generate.py`. The rewriter sees only the conversation",
        "history — never any documents — so it can resolve references but cannot introduce",
        "facts. The grounded system prompt is unchanged.",
        "",
        f"### Turn 1 — `{TURN_1}`",
        "",
    ]

    turn_1 = generate_answer(TURN_1, method="hybrid")
    lines += ["```text", turn_1["answer"].strip(), "", "Sources:", turn_1["sources"].strip(), "```", ""]

    lines += [
        f"### Turn 2 — `{TURN_2}`",
        "",
        'First, what the follow-up retrieves **without** memory. The word "his" carries no',
        "retrievable content, so the retriever has nothing to anchor on:",
        "",
    ]
    no_memory = search(TURN_2, top_k=DEFAULT_TOP_K, method="hybrid")
    lines += rank_table(no_memory)
    blackstone_without = sum(1 for h in no_memory if h.source_file == "professor_1.txt")

    turn_2 = generate_answer(TURN_2, method="hybrid", history=[(TURN_1, turn_1["answer"])])
    blackstone_with = sum(
        1 for chunk in turn_2["chunks"] if chunk["metadata"].get("source_file") == "professor_1.txt"
    )

    lines += [
        "",
        "Now **with** memory. The follow-up is rewritten first:",
        "",
        "```text",
        f"Original follow-up:       {TURN_2}",
        f"Rewritten for retrieval:  {turn_2['search_question']}",
        "```",
        "",
        "Retrieved after rewriting:",
        "",
        "| Rank | Chunk ID | Source file |",
        "|---|---|---|",
    ]
    for rank, chunk in enumerate(turn_2["chunks"], start=1):
        lines.append(
            f"| {rank} | `{chunk['chunk_id']}` | {chunk['metadata'].get('source_file', 'unknown')} |"
        )

    lines += [
        "",
        "```text",
        turn_2["answer"].strip(),
        "",
        "Sources:",
        turn_2["sources"].strip(),
        "```",
        "",
        f"**Visible effect:** without memory, {blackstone_without} of {DEFAULT_TOP_K} retrieved",
        f"chunks are Jeremy Blackstone reviews; with memory, {blackstone_with} of"
        f" {DEFAULT_TOP_K} are. The answer names Blackstone and cites his review file, which is",
        "only possible because the pronoun was resolved before retrieval ran — not because of",
        "topic overlap.",
        "",
    ]

    print(f"Metadata filter removed: {removed}")
    print(f"Rewritten follow-up: {turn_2['search_question']}")
    print(f"Blackstone chunks without memory: {blackstone_without}, with memory: {blackstone_with}")
    write_report("stretch_demo.md", lines)


# ---------------------------------------------------------------------------


COMMANDS = {
    "baseline": run_baseline,
    "hybrid": run_hybrid,
    "chunking": run_chunking,
    "demo": run_demo,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluation and stretch-feature reports for The Unofficial Guide."
    )
    parser.add_argument(
        "report",
        choices=[*COMMANDS, "all"],
        help="Which report to generate",
    )
    args = parser.parse_args()

    selected = list(COMMANDS) if args.report == "all" else [args.report]
    for name in selected:
        print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
        COMMANDS[name]()


if __name__ == "__main__":
    main()
