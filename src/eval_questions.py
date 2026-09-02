"""The 5 evaluation questions from planning.md, with hand-labeled relevance judgments.

`relevant_sources` lists the source files that genuinely contain evidence for the question.
It is deliberately conservative: for "what do students say about X" questions only the
student-review file counts, so the official faculty directory entry for that professor is
scored as noise even though it matches the name. Retrieving an email address is not
answering the question.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalQuestion:
    number: int
    question: str
    relevant_sources: frozenset[str]
    # Chunk IDs that must all be retrieved for the answer to be complete. Only set where
    # the baseline evaluation showed a recall problem worth measuring.
    required_chunk_ids: frozenset[str] = field(default_factory=frozenset)
    expect_refusal: bool = False


EVAL_QUESTIONS: tuple[EvalQuestion, ...] = (
    EvalQuestion(
        number=1,
        question="What do students say about Jiang Li's grading and exams?",
        relevant_sources=frozenset({"professor_2.txt"}),
    ),
    EvalQuestion(
        number=2,
        question="What do students say about Jeremy Blackstone?",
        relevant_sources=frozenset({"professor_1.txt"}),
        required_chunk_ids=frozenset(
            {"professor_1::review_1", "professor_1::review_2", "professor_1::review_3"}
        ),
    ),
    EvalQuestion(
        number=3,
        question="What problems have students experienced with course registration at Howard?",
        relevant_sources=frozenset(
            {"hilltop_article_1.txt", "hilltop_article_2.txt", "hilltop_article_3.txt"}
        ),
    ),
    EvalQuestion(
        number=4,
        question="Do students have consistent opinions about Gloria Washington?",
        relevant_sources=frozenset({"professor_3.txt"}),
        required_chunk_ids=frozenset({"professor_3::review_1", "professor_3::review_2"}),
    ),
    EvalQuestion(
        number=5,
        question="What do students say about the Computer Science professors at Georgetown University?",
        relevant_sources=frozenset(),
        expect_refusal=True,
    ),
)


def precision_at_k(retrieved_sources: list[str], relevant_sources: frozenset[str]) -> float | None:
    """Fraction of retrieved chunks from a relevant source file.

    None when no document in the corpus is relevant (the out-of-scope question), where
    precision is undefined and the correct behaviour is a refusal instead.
    """
    if not relevant_sources:
        return None
    if not retrieved_sources:
        return 0.0
    hits = sum(1 for source in retrieved_sources if source in relevant_sources)
    return hits / len(retrieved_sources)
