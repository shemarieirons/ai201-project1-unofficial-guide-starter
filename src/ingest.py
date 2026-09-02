from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"

ARTICLE_TARGET_TOKENS = 300
ARTICLE_OVERLAP_TOKENS = 50
ARTICLE_MIN_TAIL_TOKENS = 100


@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    source_file: str


@dataclass
class ParsedDocument:
    path: Path
    document_type: str
    chunks: list[Chunk]
    expected_chunk_count: int | None = None


def approx_token_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def normalize_inline_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_multiline_block(text: str) -> str:
    lines = []
    for line in text.replace("\r\n", "\n").split("\n"):
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines).strip()


def extract_first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.M)
    return match.group(1).strip() if match else ""


def detect_document_type(path: Path, raw_text: str) -> str:
    if re.search(r"^Professor:\s*", raw_text, re.M):
        return "professor_review"
    if re.search(r"^Source Type:\s*Official Howard University department page", raw_text, re.M):
        return "faculty_directory"
    if re.search(r"^Title:\s*", raw_text, re.M) and re.search(r"The Hilltop", raw_text, re.I):
        return "article"

    stem = path.stem.lower()
    if stem.startswith("professor_"):
        return "professor_review"
    if stem.startswith("hilltop_article_"):
        return "article"
    if "faculty_directory" in stem:
        return "faculty_directory"

    raise ValueError(f"Unable to detect document type for {path.name}")


def load_documents(data_dir: Path) -> list[tuple[Path, str, str]]:
    documents: list[tuple[Path, str, str]] = []
    for path in sorted(data_dir.glob("*.txt")):
        raw_text = path.read_text(encoding="utf-8")
        document_type = detect_document_type(path, raw_text)
        documents.append((path, raw_text, document_type))
    return documents


def build_rmp_prefix(header_block: str) -> tuple[str, dict[str, Any]]:
    professor = extract_first_match(r"^Professor:\s*(.+)$", header_block)
    department = extract_first_match(r"^Department:\s*(.+)$", header_block)
    source_line = extract_first_match(r"^Source:\s*(.+)$", header_block)
    aggregate_stats = extract_first_match(r"^Aggregate stats at time of collection:\s*(.+)$", header_block)
    url = source_line.split(" - ", 1)[1].strip() if " - " in source_line else source_line

    metadata: dict[str, Any] = {
        "source": "RateMyProfessors",
        "url": url,
        "professor": professor,
        "department": department,
        "aggregate_stats": aggregate_stats,
    }

    prefix_lines = [normalize_inline_text(line) for line in header_block.splitlines() if normalize_inline_text(line)]
    prefix = "\n".join(prefix_lines).strip()
    return prefix, metadata


def parse_rmp_chunks(path: Path, raw_text: str) -> list[Chunk]:
    parts = re.split(r"(?m)^\s*---\s*$", raw_text)
    header_block = parts[0].strip()
    review_sections = [part.strip() for part in parts[1:] if part.strip()]
    prefix, base_metadata = build_rmp_prefix(header_block)

    chunks: list[Chunk] = []
    for review_section in review_sections:
        review_number_text = extract_first_match(r"^Review\s+(\d+)\b", review_section)
        review_number = int(review_number_text) if review_number_text else 0
        course = extract_first_match(r"^Course:\s*(.+)$", review_section)
        rating_context = extract_first_match(r"^Rating context:\s*(.+)$", review_section)
        review_text = normalize_multiline_block(review_section)
        chunk_text = f"{prefix}\n\n{review_text}".strip()
        metadata = {
            **base_metadata,
            "document_type": "professor_review",
            "review_number": review_number,
            "course": course,
            "rating_context": rating_context,
            "source_file": path.name,
        }
        chunks.append(
            Chunk(
                chunk_id=f"{path.stem}::review_{review_number}",
                text=chunk_text,
                metadata=metadata,
                source_file=path.name,
            )
        )

    return chunks


def chunk_paragraphs_with_overlap(paragraphs: list[str], target_tokens: int, overlap_tokens: int) -> list[list[str]]:
    if not paragraphs:
        return []

    total_tokens = sum(approx_token_count(paragraph) for paragraph in paragraphs)
    if total_tokens <= target_tokens:
        return [paragraphs]

    chunks: list[list[str]] = []
    start = 0
    while start < len(paragraphs):
        current: list[str] = []
        current_tokens = 0
        end = start

        while end < len(paragraphs):
            paragraph = paragraphs[end]
            paragraph_tokens = approx_token_count(paragraph)
            if current and current_tokens + paragraph_tokens > target_tokens:
                break
            current.append(paragraph)
            current_tokens += paragraph_tokens
            end += 1
            if current_tokens >= target_tokens:
                break

        if not current:
            current = [paragraphs[end]]
            end += 1

        remaining_tokens = sum(approx_token_count(paragraph) for paragraph in paragraphs[end:])
        if remaining_tokens and remaining_tokens < ARTICLE_MIN_TAIL_TOKENS:
            current.extend(paragraphs[end:])
            chunks.append(current)
            break

        chunks.append(current)

        if end >= len(paragraphs):
            break

        overlap_start = end
        overlap_accum = 0
        while overlap_start > start and overlap_accum < overlap_tokens:
            overlap_start -= 1
            overlap_accum += approx_token_count(paragraphs[overlap_start])

        next_start = overlap_start if overlap_start > start else end
        if next_start <= start:
            next_start = start + 1
        start = next_start

    return chunks


def parse_hilltop_chunks(path: Path, raw_text: str) -> list[Chunk]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", raw_text.strip()) if block.strip()]
    if not blocks:
        return []

    header_block = blocks[0]
    body_paragraphs = [normalize_inline_text(block) for block in blocks[1:] if normalize_inline_text(block)]

    title = extract_first_match(r"^Title:\s*(.+)$", header_block)
    source_line = extract_first_match(r"^Source:\s*(.+)$", header_block)
    date = extract_first_match(r"^Date:\s*(.+)$", header_block)

    prefix_lines = [
        "Source Type: Student newspaper article (The Hilltop)",
        f"Title: {title}" if title else "Title:",
        f"Source: {source_line}" if source_line else "Source:",
        f"Date: {date}" if date else "Date:",
    ]
    prefix = "\n".join(prefix_lines).strip()

    paragraph_chunks = chunk_paragraphs_with_overlap(body_paragraphs, ARTICLE_TARGET_TOKENS, ARTICLE_OVERLAP_TOKENS)
    chunks: list[Chunk] = []
    for index, paragraph_group in enumerate(paragraph_chunks, start=1):
        chunk_text = f"{prefix}\n\n" + "\n\n".join(paragraph_group)
        metadata = {
            "source": "The Hilltop",
            "document_type": "article",
            "article": path.name,
            "chunk_id": index,
            "title": title,
            "url": source_line,
            "date": date,
            "source_file": path.name,
        }
        chunks.append(
            Chunk(
                chunk_id=f"{path.stem}::chunk_{index}",
                text=chunk_text.strip(),
                metadata=metadata,
                source_file=path.name,
            )
        )

    return chunks


def parse_faculty_directory_chunks(path: Path, raw_text: str) -> list[Chunk]:
    lines = [line.strip() for line in raw_text.replace("\r\n", "\n").splitlines() if line.strip()]
    entry_lines = [line for line in lines if line.startswith("-")]

    department = extract_first_match(r"^Department:\s*(.+)$", raw_text)
    source_url = extract_first_match(r"^Source:\s*(.+)$", raw_text)
    short_source_line = "Source: Howard University EECS faculty directory"
    if source_url:
        short_source_line = f"{short_source_line} ({source_url})"
    if department:
        short_source_line = f"{short_source_line}\nDepartment: {department}"

    chunks: list[Chunk] = []
    for index, entry_line in enumerate(entry_lines, start=1):
        entry_text = entry_line.lstrip("-").strip()
        if " - " in entry_text:
            name_part, detail_part = entry_text.split(" - ", 1)
        else:
            name_part, detail_part = entry_text, ""

        name = normalize_inline_text(name_part)
        chunk_lines = [short_source_line, f"Faculty: {name}"]
        if detail_part:
            chunk_lines.append(normalize_inline_text(detail_part))
        chunk_text = "\n".join(line for line in chunk_lines if line).strip()
        metadata = {
            "source": "Howard University EECS",
            "document_type": "faculty_directory",
            "professor": name,
            "source_file": path.name,
            "directory_entry": index,
            "raw_entry": entry_text,
        }
        safe_name = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "faculty"
        chunks.append(
            Chunk(
                chunk_id=f"{path.stem}::{index:02d}_{safe_name}",
                text=chunk_text,
                metadata=metadata,
                source_file=path.name,
            )
        )

    return chunks


def parse_document(path: Path, raw_text: str, document_type: str) -> ParsedDocument:
    if document_type == "professor_review":
        chunks = parse_rmp_chunks(path, raw_text)
        expected_chunk_count = len([part for part in re.split(r"(?m)^\s*---\s*$", raw_text) if part.strip()]) - 1
    elif document_type == "article":
        chunks = parse_hilltop_chunks(path, raw_text)
        expected_chunk_count = None
    elif document_type == "faculty_directory":
        chunks = parse_faculty_directory_chunks(path, raw_text)
        expected_chunk_count = len([line for line in raw_text.splitlines() if line.strip().startswith("-")])
    else:
        raise ValueError(f"Unsupported document type: {document_type}")

    return ParsedDocument(path=path, document_type=document_type, chunks=chunks, expected_chunk_count=expected_chunk_count)


def validate_chunks(documents: list[ParsedDocument]) -> None:
    errors: list[str] = []

    for document in documents:
        if document.expected_chunk_count is not None and len(document.chunks) != document.expected_chunk_count:
            errors.append(
                f"{document.path.name}: expected {document.expected_chunk_count} chunks, found {len(document.chunks)}"
            )

        if document.document_type == "faculty_directory" and len(document.chunks) == 1:
            errors.append(f"{document.path.name}: directory was collapsed into a single chunk")

        for chunk in document.chunks:
            text = chunk.text.strip()
            if not text:
                errors.append(f"{chunk.chunk_id}: empty chunk")
                continue

            if chunk.metadata.get("document_type") == "professor_review":
                professor = chunk.metadata.get("professor", "")
                review_headings = re.findall(r"(?m)^Review\s+\d+\b", text)
                if not professor or professor not in text:
                    errors.append(f"{chunk.chunk_id}: missing professor name in RMP chunk")
                if len(review_headings) != 1:
                    errors.append(f"{chunk.chunk_id}: review boundary problem, found {len(review_headings)} review headings")

            if chunk.metadata.get("document_type") == "faculty_directory":
                professor = chunk.metadata.get("professor", "")
                if not professor or professor not in text:
                    errors.append(f"{chunk.chunk_id}: faculty chunk missing professor name")

    if errors:
        raise ValueError("\n".join(errors))


def render_preview(text: str, max_chars: int = 150) -> str:
    preview = normalize_inline_text(text.replace("\n", " "))
    return preview[:max_chars] + ("..." if len(preview) > max_chars else "")


def print_debug_report(documents: list[ParsedDocument]) -> None:
    all_chunks = [chunk for document in documents for chunk in document.chunks]
    chunk_counts = Counter(chunk.metadata["document_type"] for chunk in all_chunks)

    print(f"Documents loaded: {len(documents)}")
    print(f"Chunks created: {len(all_chunks)}")
    print("Chunks by document type:")
    for document_type, count in sorted(chunk_counts.items()):
        print(f"  - {document_type}: {count}")

    print("\nChunk details:")
    for chunk in all_chunks:
        word_count = approx_token_count(chunk.text)
        print(f"- chunk_id: {chunk.chunk_id}")
        print(f"  source/file: {chunk.source_file}")
        print(f"  metadata: {chunk.metadata}")
        print(f"  approx_token_count: {word_count}")
        print(f"  preview: {render_preview(chunk.text)}")


def ingest_documents(data_dir: Path = DATA_DIR) -> list[dict[str, Any]]:
    loaded_documents = load_documents(data_dir)
    parsed_documents = [parse_document(path, raw_text, document_type) for path, raw_text, document_type in loaded_documents]
    validate_chunks(parsed_documents)
    print_debug_report(parsed_documents)

    structured_chunks: list[dict[str, Any]] = []
    for document in parsed_documents:
        for chunk in document.chunks:
            structured_chunks.append(
                {
                    "id": chunk.chunk_id,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                    "source_file": chunk.source_file,
                }
            )
    return structured_chunks


def main() -> None:
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"Data directory not found: {DATA_DIR}")
    ingest_documents(DATA_DIR)


if __name__ == "__main__":
    main()