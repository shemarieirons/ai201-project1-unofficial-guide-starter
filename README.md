# The Unofficial Guide — Project 1

## Overview
This project covers Howard University course and professor guidance. It answers questions using a corpus of student reviews, Howard’s EECS faculty directory, and The Hilltop articles. The system is a retrieval-augmented generation pipeline, so answers are grounded in retrieved documents rather than outside knowledge.

## Document Sources
| # | Source | Type | URL or file path |
|---|---|---|---|
| 1 | Jeremy Blackstone | RateMyProfessors | data/professor_1.txt |
| 2 | Jiang Li | RateMyProfessors | data/professor_2.txt |
| 3 | Gloria Washington | RateMyProfessors | data/professor_3.txt |
| 4 | Noha Hazzazi | RateMyProfessors | data/professor_4.txt |
| 5 | Anamika Rupa | RateMyProfessors | data/professor_5.txt |
| 6 | John Harris | RateMyProfessors | data/professor_6.txt |
| 7 | EECS faculty directory | Howard official directory | data/faculty_directory_eecs.txt |
| 8 | Spring registration delays | The Hilltop | data/hilltop_article_1.txt |
| 9 | Unassigned professors/classrooms | The Hilltop | data/hilltop_article_2.txt |
| 10 | Enrollment growth and staffing | The Hilltop | data/hilltop_article_3.txt |

## Architecture
Source Documents → Document Ingestion / Cleaning → Chunking → Embeddings → ChromaDB → Semantic Retrieval (Top 5) → Retrieved Context → Groq LLM → Grounded Answer + Sources → Gradio Interface

## Ingestion and Chunking
RateMyProfessors files are chunked one review per chunk with no overlap. This preserves each student opinion as a complete unit.

The Hilltop articles are chunked at approximately 300 tokens with approximately 50 tokens of overlap where needed. This fits longer news articles and helps keep related reporting together across paragraph boundaries.

The EECS directory is chunked one faculty entry per chunk with no overlap. This keeps the structured roster data intact.

Before chunking, the ingester normalizes whitespace and line breaks and adds source metadata to each chunk. The final corpus contains 47 chunks.

## Sample Chunks
| # | Source document | Chunk text |
|---|---|---|
| 1 | professor_1.txt | Professor: Jeremy Blackstone; Review 2: “Calls him the best computer science professor the reviewer has had… genuinely wants students to learn… sets them up for their career beyond Howard.” |
| 2 | professor_2.txt | Professor: Jiang Li; Review 1: “Describes the class as very hard… online homework as the worst part… Exams mirror the homework format with different numbers.” |
| 3 | faculty_directory_eecs.txt | Source: Howard University EECS faculty directory; Faculty: Jeremy Blackstone; jeremy.m.blackstone@howard.edu |
| 4 | hilltop_article_1.txt | Students reported having to refresh the registration website repeatedly because new seats open without notification. |
| 5 | hilltop_article_2.txt | Multiple students reported courses with no assigned professor or classroom, and manual input in Coursedog was a contributing factor. |

## Embeddings and Retrieval
The embedding model is `all-MiniLM-L6-v2` through `sentence-transformers`. ChromaDB is the persistent vector store, and retrieval uses semantic similarity to return the top 5 chunks while preserving metadata for source attribution.

Retrieval testing showed the expected behavior for the Jiang Li query, which returned relevant grading and exam chunks. The Jeremy Blackstone query returned one relevant review first, but it also brought in unrelated cross-professor chunks, which contributed to the documented failure. The Howard registration query returned relevant Hilltop chunks about delays, missing notifications, and staffing problems.

## Grounded Generation
Groq is used for generation. The LLM receives only the retrieved context, and the prompt instructs it not to use outside knowledge, not to invent facts, to acknowledge disagreement when reviews conflict, and to refuse when the retrieved context is insufficient.

Source attribution comes from the retrieved chunk metadata, and cited chunk IDs are used to form the returned source list. Out-of-scope questions are refused with the insufficient-information response.

## Query Interface
The Gradio interface has a question input, a submit action, a grounded answer field, and a supporting sources field.

For an out-of-scope example, the Georgetown question returns the refusal message: “I don't have enough information in the provided sources to answer that question.”

## Evaluation Report
| # | Question | Ground Truth | Actual Answer | Judgment |
|---|---|---|---|---|
| 1 | What do students say about Jiang Li’s grading and exams? | Reviews describe harsh, unclear grading, very difficult homework, exams that mirror homework, and lecture material that does not always match what is tested. | The answer says grading is strict and opaque, homework is heavy, and exams mirror homework and sometimes test material not covered in lecture. | Pass |
| 2 | What do students say about Jeremy Blackstone? | Reviews are mostly positive and career-focused, but there is also at least one negative comment about slow grading and disorganization near finals. | The answer describes him as very positive and useful for career preparation, but it omits the negative review. | Fail |
| 3 | What problems have students experienced with course registration at Howard? | Students report delayed access to classes, no seat-open notifications, unclear communication, advisor problems, and stress about graduation timing. | The answer covers registration delays, lack of notifications, advising gaps, and enrollment pressure. | Pass |
| 4 | Do students have consistent opinions about Gloria Washington? | No. The reviews are mixed, with negative comments about exact-answer grading and positive comments about fairness and extra credit. | The answer says opinions are mixed and contrasts a negative review with a positive one. | Pass |
| 5 | What contributed to registration and staffing problems at Howard? | Rising enrollment, faculty turnover, manual Coursedog data entry, advisor availability problems, and weak registration communication all contributed. | The answer lists the same structural causes and connects them to staffing and registration delays. | Pass |

The results include four passes and one documented failure.

## Failure Case Analysis
The Jeremy Blackstone case is a retrieval failure, not a hallucination or generation failure. The corpus contained both positive and negative student reviews for Jeremy Blackstone, and the negative review exists in `professor_1.txt`. That negative review was not included in the top-5 retrieved chunks for the evaluation query, so the generator only had positive evidence available in its retrieved context. The generated answer was grounded in the retrieved evidence, but it was incomplete relative to the full corpus and overstated the overall student consensus.

A reasonable improvement would be better same-professor coverage, reranking, metadata filtering, or another retrieval strategy. Those improvements were not implemented for this assignment.

## Spec Reflection
The implementation stays aligned with `planning.md`. It uses the planned ingestion and cleaning, deliberate chunking, sentence-transformer embeddings, ChromaDB, top-5 semantic retrieval, Groq generation, grounded answers, source attribution, and the Gradio interface.

The evaluation also follows the planned workflow: five test questions, document-based ground truth, actual generated answers, and an explicit pass/fail judgment for each case.

## AI Usage
AI tools were used to inspect the project specification and planning document, assist with implementation and debugging, inspect retrieval outputs, and help structure the evaluation documentation.

The evaluation results were checked against the actual retrieved outputs and source documents rather than accepted blindly from AI.

## Production Reflection
Possible future improvements would include a stronger or larger embedding model, reranking, better same-entity retrieval coverage, hybrid retrieval, and metadata filtering. These are not implemented stretch features in this submission.
