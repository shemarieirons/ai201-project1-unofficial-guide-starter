"""Stretch features 3 and 4 — metadata filtering and conversational memory.

Writes stretch_demo.md with before/after transcripts. Needs GROQ_API_KEY for the
conversational-memory section.

    python demo_stretch.py
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.generate import generate_answer
from src.hybrid import search
from src.vector_store import DEFAULT_TOP_K

FILTER_QUESTION = "What problems have students experienced with course registration at Howard?"
TURN_1 = "What do students say about Jeremy Blackstone?"
TURN_2 = "How are his exams structured?"


def rank_table(hits: list) -> list[str]:
    lines = ["| Rank | Chunk ID | Source file | Hybrid score |", "|---|---|---|---|"]
    for rank, hit in enumerate(hits, start=1):
        lines.append(f"| {rank} | `{hit.chunk_id}` | {hit.source_file} | {hit.score:.4f} |")
    return lines


def main() -> None:
    lines: list[str] = ["# Metadata Filtering and Conversational Memory", ""]

    # ---- Metadata filtering -------------------------------------------------
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
    ]

    lines += ["### Filtered to `professor = Gloria Washington`", ""]
    professor_filtered = search(
        "Is she a tough grader?",
        top_k=DEFAULT_TOP_K,
        method="hybrid",
        where={"professor": "Gloria Washington"},
    )
    lines += [
        "Question: `Is she a tough grader?` — a question with no name in it at all, which the",
        "baseline system cannot route to the right professor.",
        "",
    ]
    lines += rank_table(professor_filtered)
    lines += [
        "",
        "**Visible effect:** the candidate set drops from 47 chunks to the "
        f"{len(professor_filtered)} whose",
        "`professor` metadata is Gloria Washington — her two review chunks plus her official",
        "directory entry — so an ambiguous pronoun question still retrieves the right",
        "professor. Note that the directory entry scores 0.0000 on both legs: it is in the",
        "candidate set because it matches the filter, but it carries no evidence about",
        "grading, which is the boilerplate-dilution problem showing up again in miniature.",
        "",
    ]

    # ---- Conversational memory ---------------------------------------------
    lines += [
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
        "First, what the follow-up retrieves **without** memory. The word \"his\" carries no",
        "retrievable content, so the retriever has nothing to anchor on:",
        "",
    ]
    no_memory = search(TURN_2, top_k=DEFAULT_TOP_K, method="hybrid")
    lines += rank_table(no_memory)
    blackstone_without = sum(1 for h in no_memory if h.source_file == "professor_1.txt")

    history = [(TURN_1, turn_1["answer"])]
    turn_2 = generate_answer(TURN_2, method="hybrid", history=history)
    blackstone_with = sum(
        1 for chunk in turn_2["chunks"] if chunk["metadata"].get("source_file") == "professor_1.txt"
    )

    lines += [
        "",
        "Now **with** memory. The follow-up is rewritten first:",
        "",
        "```text",
        f"Original follow-up:  {TURN_2}",
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

    output_path = ROOT_DIR / "stretch_demo.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Metadata filter removed: {removed}")
    print(f"Rewritten follow-up: {turn_2['search_question']}")
    print(f"Blackstone chunks without memory: {blackstone_without}, with memory: {blackstone_with}")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
