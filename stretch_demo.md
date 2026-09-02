# Metadata Filtering and Conversational Memory

## Metadata filtering

Question: `What problems have students experienced with course registration at Howard?`

Every chunk carries `source`, `document_type`, and `professor` metadata from
ingestion. The filter is passed to ChromaDB's native `where` clause for the semantic
leg and applied to the BM25 candidate set for the keyword leg, so hybrid search
honours it too.

### Unfiltered

| Rank | Chunk ID | Source file | Hybrid score |
|---|---|---|---|
| 1 | `hilltop_article_1::chunk_1` | hilltop_article_1.txt | 1.0000 |
| 2 | `hilltop_article_3::chunk_1` | hilltop_article_3.txt | 0.8931 |
| 3 | `hilltop_article_2::chunk_1` | hilltop_article_2.txt | 0.7580 |
| 4 | `professor_3::review_1` | professor_3.txt | 0.4579 |
| 5 | `professor_4::review_4` | professor_4.txt | 0.4416 |

### Filtered to `source = The Hilltop`

| Rank | Chunk ID | Source file | Hybrid score |
|---|---|---|---|
| 1 | `hilltop_article_1::chunk_1` | hilltop_article_1.txt | 1.0000 |
| 2 | `hilltop_article_3::chunk_1` | hilltop_article_3.txt | 0.5550 |
| 3 | `hilltop_article_2::chunk_1` | hilltop_article_2.txt | 0.0000 |

**Visible effect:** the filter removed 2 chunk(s) — `professor_3::review_1`, `professor_4::review_4` — leaving only student-newspaper evidence. Those were the professor-review chunks
that the baseline evaluation identified as noise on this question.

### Filtered to `professor = Gloria Washington`

Question: `Is she a tough grader?` — a question with no name in it at all, which the
baseline system cannot route to the right professor.

| Rank | Chunk ID | Source file | Hybrid score |
|---|---|---|---|
| 1 | `professor_3::review_2` | professor_3.txt | 1.0000 |
| 2 | `professor_3::review_1` | professor_3.txt | 0.8618 |
| 3 | `faculty_directory_eecs::19_gloria_washington` | faculty_directory_eecs.txt | 0.0000 |

**Visible effect:** the candidate set drops from 47 chunks to the 3 whose
`professor` metadata is Gloria Washington — her two review chunks plus her official
directory entry — so an ambiguous pronoun question still retrieves the right
professor. Note that the directory entry scores 0.0000 on both legs: it is in the
candidate set because it matches the filter, but it carries no evidence about
grading, which is the boilerplate-dilution problem showing up again in miniature.

## Conversational memory

Follow-ups are resolved into standalone questions *before* retrieval, by
`rewrite_followup()` in `src/generate.py`. The rewriter sees only the conversation
history — never any documents — so it can resolve references but cannot introduce
facts. The grounded system prompt is unchanged.

### Turn 1 — `What do students say about Jeremy Blackstone?`

```text
Students who have posted reviews of Professor Jeremy Blackstone on RateMyProfessors share mixed experiences:

* **Positive impressions** – Two reviewers praise him highly. One calls him “the best computer‑science professor” they have had, noting that he “genuinely wants students to learn” and helps set them up for their careers beyond Howard, and mentions that participation matters, extra credit is offered, and grading criteria are clear【professor_1::review_2】. Another describes him as “the most simplistic and straightforward” professor, saying that all assignments are posted at the start of the term, are few and not difficult, and allow students to work at their own pace. This reviewer also calls the class “the most carefree” they have taken, with exams mirroring the homework and clear grading criteria【professor_1::review_1】.

* **Negative impression** – A third reviewer, who labels their comment as an outlier, reports a very different experience. They say the semester was “embarrassingly disorganized,” with only one assignment graded by finals week, “lazy” lecture slides, and a mishap where the professor posted the wrong final exam and then changed the exam questions without clearly informing students【professor_1::review_3】.

Thus, while most student reviews highlight Blackstone’s clear organization, supportive attitude, and straightforward coursework, at least one student felt the class was poorly managed and confusing.

Sources:
1. professor_1.txt — RateMyProfessors (Jeremy Blackstone, Computer Science / Electrical Engineering and Computer Science)
```

### Turn 2 — `How are his exams structured?`

First, what the follow-up retrieves **without** memory. The word "his" carries no
retrievable content, so the retriever has nothing to anchor on:

| Rank | Chunk ID | Source file | Hybrid score |
|---|---|---|---|
| 1 | `professor_2::review_1` | professor_2.txt | 0.9404 |
| 2 | `professor_1::review_1` | professor_1.txt | 0.9233 |
| 3 | `professor_4::review_3` | professor_4.txt | 0.7922 |
| 4 | `professor_2::review_4` | professor_2.txt | 0.7208 |
| 5 | `professor_6::review_2` | professor_6.txt | 0.7131 |

Now **with** memory. The follow-up is rewritten first:

```text
Original follow-up:  How are his exams structured?
Rewritten for retrieval:  How are Jeremy Blackstone's exams structured?
```

Retrieved after rewriting:

| Rank | Chunk ID | Source file |
|---|---|---|
| 1 | `professor_1::review_1` | professor_1.txt |
| 2 | `professor_1::review_3` | professor_1.txt |
| 3 | `professor_1::review_2` | professor_1.txt |
| 4 | `professor_4::review_3` | professor_4.txt |
| 5 | `professor_2::review_1` | professor_2.txt |

```text
The reviewer who described Professor Jeremy Blackstone as “the most simplistic and straightforward professor” said that his exams are formatted the same way as the homework assignments—i.e., they follow the same structure and style as the regular coursework assignments posted at the start of the term【professor_1::review_1】.

Sources:
1. professor_1.txt — RateMyProfessors (Jeremy Blackstone, Computer Science / Electrical Engineering and Computer Science)
```

**Visible effect:** without memory, 1 of 5 retrieved
chunks are Jeremy Blackstone reviews; with memory, 3 of 5 are. The answer names Blackstone and cites his review file, which is
only possible because the pronoun was resolved before retrieval ran — not because of
topic overlap.
