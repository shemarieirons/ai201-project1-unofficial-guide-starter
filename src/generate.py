from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from groq import Groq


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.retrieve import retrieve
from src.vector_store import DEFAULT_TOP_K


ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_NAME = "openai/gpt-oss-120b"
INSUFFICIENT_INFO_RESPONSE = "I don't have enough information in the provided sources to answer that question."

SYSTEM_PROMPT = """You are a grounded question-answering assistant for Howard University course and professor documents.

Rules:
- Answer ONLY using the retrieved context.
- Do not use outside knowledge.
- Do not invent facts.
- If the retrieved context does not contain enough information, say: "I don't have enough information in the provided sources to answer that question."
- Student reviews represent individual student experiences and opinions, not objective facts.
- When reviews disagree, explicitly acknowledge the disagreement.
- Do not present a reviewer's opinion as a universal fact.
- Distinguish official Howard University information from student-reported information.
- Use the retrieved source information when explaining the answer.
- If the question asks about an institution or topic that is not supported by the retrieved context, refuse with the insufficient-information sentence above.
- When you use a retrieved chunk to support a claim, cite its chunk ID inline using [chunk_id].
"""


def load_groq_client() -> Groq:
    load_dotenv(ROOT_DIR / ".env")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set. Add it to .env before running the app.")
    return Groq(api_key=api_key)


def extract_retrieved_chunks(results: dict[str, Any]) -> list[dict[str, Any]]:
    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    chunks: list[dict[str, Any]] = []
    for index, chunk_id in enumerate(ids):
        chunks.append(
            {
                "rank": index + 1,
                "chunk_id": chunk_id,
                "text": documents[index] if index < len(documents) else "",
                "metadata": dict(metadatas[index]) if index < len(metadatas) else {},
                "distance": distances[index] if index < len(distances) else None,
            }
        )
    return chunks


def describe_source(metadata: dict[str, Any]) -> str:
    source_file = metadata.get("source_file", "unknown source")
    source = metadata.get("source", "")

    if source == "RateMyProfessors":
        details = [value for value in [metadata.get("professor"), metadata.get("department")] if value]
        if details:
            return f"{source_file} — {source} ({', '.join(details)})"
        return f"{source_file} — {source}"

    if source == "The Hilltop":
        title = metadata.get("title", "")
        if title:
            return f"{source_file} — {source} ({title})"
        return f"{source_file} — {source}"

    if source:
        return f"{source_file} — {source}"

    return source_file


def build_sources_text(chunks: list[dict[str, Any]]) -> str:
    seen: set[str] = set()
    ordered_sources: list[str] = []

    for chunk in chunks:
        label = describe_source(chunk.get("metadata", {}))
        if label not in seen:
            seen.add(label)
            ordered_sources.append(label)

    if not ordered_sources:
        return "No sources returned."

    return "\n".join(f"{index}. {label}" for index, label in enumerate(ordered_sources, start=1))


def is_refusal(answer_text: str) -> bool:
    """True only when the answer is the refusal sentence itself.

    A substring check would also match a partial answer such as "I don't have enough
    information ... about the exam format, but reviewers do say X", which does cite real
    retrieved chunks and must keep its source list.
    """
    normalized = answer_text.strip().strip("\"'").rstrip()
    return normalized.startswith(INSUFFICIENT_INFO_RESPONSE) and len(
        normalized
    ) <= len(INSUFFICIENT_INFO_RESPONSE) + 1


def extract_cited_chunk_ids(answer_text: str) -> list[str]:
    citation_pattern = re.compile(r"(?:\[|【)\s*([A-Za-z0-9_:\-]+)\s*(?:\]|】)")
    return citation_pattern.findall(answer_text)


def format_chunk_context(chunk: dict[str, Any]) -> str:
    metadata = chunk.get("metadata", {})
    lines = [
        f"[Chunk {chunk.get('rank', '?')}]",
        f"Chunk ID: {chunk.get('chunk_id', 'unknown')}",
        f"Source: {describe_source(metadata)}",
    ]

    helpful_keys = ["professor", "department", "course", "review_number", "title", "date", "rating_context"]
    extra_fields = []
    for key in helpful_keys:
        value = metadata.get(key)
        if value not in {None, ""}:
            extra_fields.append(f"{key}: {value}")
    if extra_fields:
        lines.append("Metadata:")
        lines.extend(f"  - {field}" for field in extra_fields)

    lines.append("Text:")
    lines.append(chunk.get("text", "").strip())
    return "\n".join(lines)


def build_retrieved_context(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "No retrieved context was returned."

    formatted_chunks = [format_chunk_context(chunk) for chunk in chunks]
    return "Retrieved context:\n\n" + "\n\n---\n\n".join(formatted_chunks)


def generate_answer(question: str, top_k: int = DEFAULT_TOP_K) -> dict[str, Any]:
    results = retrieve(question, top_k=top_k)
    chunks = extract_retrieved_chunks(results)
    context = build_retrieved_context(chunks)
    sources_text = build_sources_text(chunks)

    client = load_groq_client()
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Question:\n{question}\n\n"
                    f"{context}\n\n"
                    "Answer the question using only the retrieved context. "
                    "If the context is insufficient, use the exact insufficient-information sentence."
                ),
            },
        ],
    )

    answer_text = completion.choices[0].message.content.strip()
    if not answer_text:
        answer_text = INSUFFICIENT_INFO_RESPONSE

    if is_refusal(answer_text):
        sources_text = "None — the retrieved sources do not contain enough information to answer the question."
        return {
            "question": question,
            "answer": answer_text,
            "sources": sources_text,
            "chunks": chunks,
            "retrieved_context": context,
        }

    cited_chunk_ids = extract_cited_chunk_ids(answer_text)
    if cited_chunk_ids:
        chunk_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
        cited_chunks = [chunk_by_id[chunk_id] for chunk_id in cited_chunk_ids if chunk_id in chunk_by_id]
        if cited_chunks:
            sources_text = build_sources_text(cited_chunks)

    return {
        "question": question,
        "answer": answer_text,
        "sources": sources_text,
        "chunks": chunks,
        "retrieved_context": context,
    }


def format_cli_output(result: dict[str, Any]) -> str:
    return (
        f"Question: {result['question']}\n\n"
        f"Answer:\n{result['answer']}\n\n"
        f"Sources:\n{result['sources']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a grounded answer using retrieved Howard University sources.")
    parser.add_argument("question", nargs="?", help="Question to answer")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of chunks to retrieve")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    args = parser.parse_args()

    question = args.question or input("Enter a question: ").strip()
    if not question:
        raise ValueError("A question is required.")

    result = generate_answer(question, top_k=args.top_k)
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        print(format_cli_output(result))


if __name__ == "__main__":
    main()