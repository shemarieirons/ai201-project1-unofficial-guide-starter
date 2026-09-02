from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.generate import generate_answer
from src.retrieve import retrieve
from src.vector_store import DEFAULT_TOP_K, get_collection


QUESTIONS = [
    "What do students say about Jiang Li's grading and exams?",
    "What do students say about Jeremy Blackstone?",
    "What problems have students experienced with course registration at Howard?",
    "Do students have consistent opinions about Gloria Washington?",
    "What do students say about the Computer Science professors at Georgetown University?",
]


def _first_result_list(results: dict[str, Any], key: str) -> list[Any]:
    values = results.get(key, [[]])
    if not values:
        return []

    first_value = values[0]
    return list(first_value) if isinstance(first_value, list) else []


def _format_chunk(chunk_number: int, source_file: str, distance: Any, text: str) -> str:
    distance_text = f"{distance:.6f}" if isinstance(distance, (int, float)) else "unknown"
    return (
        f"#### Chunk {chunk_number}\n\n"
        f"- Source file: {source_file}\n"
        f"- Distance: {distance_text}\n\n"
        "```text\n"
        f"{text.strip()}\n"
        "```\n"
    )


def _format_question_section(question: str, retrieved: dict[str, Any], generated: dict[str, Any], total_chunks: int) -> str:
    ids = _first_result_list(retrieved, "ids")
    documents = _first_result_list(retrieved, "documents")
    metadatas = _first_result_list(retrieved, "metadatas")
    distances = _first_result_list(retrieved, "distances")

    lines: list[str] = [f"## Question\n\n{question}\n", f"Total chunk count: {total_chunks}\n", "### Retrieved Chunks\n"]

    if not ids:
        lines.append("No chunks returned.\n")
    else:
        for index, _chunk_id in enumerate(ids, start=1):
            document = documents[index - 1] if index - 1 < len(documents) else ""
            metadata = metadatas[index - 1] if index - 1 < len(metadatas) else {}
            distance = distances[index - 1] if index - 1 < len(distances) else None
            source_file = metadata.get("source_file", "unknown") if isinstance(metadata, dict) else "unknown"
            lines.append(_format_chunk(index, str(source_file), distance, str(document or "")))

    lines.append("### Generated Answer\n")
    lines.append("```text")
    lines.append(str(generated["answer"]).strip())
    lines.append("```\n")

    lines.append("### Source List\n")
    sources = str(generated.get("sources", "")).strip()
    if sources:
        lines.append("```text")
        lines.append(sources)
        lines.append("```\n")
    else:
        lines.append("No sources returned.\n")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    total_chunks = get_collection().count()
    output_path = ROOT_DIR / "eval_output.md"

    markdown_sections = [f"# Evaluation Dump\n\nTotal chunk count: {total_chunks}\n"]

    print(f"Total chunk count: {total_chunks}")
    print()

    for question in QUESTIONS:
        # Pinned to semantic-only: this is the baseline evaluation reported in the README,
        # and it must stay reproducible after hybrid search became the runtime default.
        retrieved = retrieve(question, top_k=DEFAULT_TOP_K)
        generated = generate_answer(question, top_k=DEFAULT_TOP_K, method="semantic")

        markdown_sections.append(_format_question_section(question, retrieved, generated, total_chunks))

        print(question)
        print(f"Total chunk count: {total_chunks}")

        ids = _first_result_list(retrieved, "ids")
        documents = _first_result_list(retrieved, "documents")
        metadatas = _first_result_list(retrieved, "metadatas")
        distances = _first_result_list(retrieved, "distances")

        for index, _chunk_id in enumerate(ids, start=1):
            document = documents[index - 1] if index - 1 < len(documents) else ""
            metadata = metadatas[index - 1] if index - 1 < len(metadatas) else {}
            distance = distances[index - 1] if index - 1 < len(distances) else None
            source_file = metadata.get("source_file", "unknown") if isinstance(metadata, dict) else "unknown"
            distance_text = f"{distance:.6f}" if isinstance(distance, (int, float)) else "unknown"
            print(f"  Chunk {index}: {source_file} | distance={distance_text}")
            print(str(document or "").strip())
            print()

        print("Generated answer:")
        print(str(generated["answer"]).strip())
        print("Sources:")
        print(str(generated.get("sources", "")).strip())
        print()

    output_path.write_text("\n".join(markdown_sections).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote evaluation dump to {output_path}")


if __name__ == "__main__":
    main()