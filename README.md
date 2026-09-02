# The Unofficial Guide — Project 1

Howard University Course and Professor Guide — a retrieval-augmented generation system over
student reviews, Howard's official EECS faculty directory, and The Hilltop student newspaper.

**Demo video:** _TODO — paste the 3–5 minute video link here before submitting._

---

## Setup and How to Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then paste your Groq API key into .env
```

Then build the index and launch the interface:

```bash
python src/embed.py         # ingest + chunk + embed into ChromaDB (run this first)
python src/app.py           # Gradio UI at http://localhost:7860
```

Other entry points:

```bash
python src/ingest.py                      # chunk-by-chunk debug report, no embedding
python src/retrieve.py "your question"    # retrieval only, prints distances + chunk text
python src/generate.py "your question"    # full grounded answer in the terminal
python eval_dump.py                       # regenerate eval_output.md for all 5 test questions
```

`src/embed.py` must be run before `src/app.py` on a fresh clone — the `.chroma/` directory is
gitignored, so the vector store is built locally rather than committed.

---

## Domain

This project covers Howard University course and professor guidance. This knowledge is
valuable and hard to find officially because Howard's catalog and department pages only
describe what a course covers, not how the professor teaches it — grading style, exam
format, workload, and whether lectures actually prepare you for the tests. That information
is instead scattered across RateMyProfessors, student journalism, and word of mouth, and a
new or transfer student would not know where to look. The system answers questions using
only the collected documents, so answers are grounded in what students and reporters
actually wrote rather than in the model's general knowledge.

---

## Document Sources

| # | Source | Type | File | URL |
|---|---|---|---|---|
| 1 | Jeremy Blackstone | RateMyProfessors | data/professor_1.txt | https://www.ratemyprofessors.com/professor/2640220 |
| 2 | Jiang Li | RateMyProfessors | data/professor_2.txt | https://www.ratemyprofessors.com/professor/2323879 |
| 3 | Gloria Washington | RateMyProfessors | data/professor_3.txt | https://www.ratemyprofessors.com/professor/2084505 |
| 4 | Noha Hazzazi | RateMyProfessors | data/professor_4.txt | https://www.ratemyprofessors.com/professor/2418869 |
| 5 | Anamika Rupa | RateMyProfessors | data/professor_5.txt | https://www.ratemyprofessors.com/professor/2976470 |
| 6 | John Harris | RateMyProfessors | data/professor_6.txt | https://www.ratemyprofessors.com/professor/2434383 |
| 7 | EECS faculty directory | Howard official directory | data/faculty_directory_eecs.txt | https://cea.howard.edu/academics/departments/electrical-engineering-and-computer-science/people-eecs |
| 8 | Spring registration delays | The Hilltop | data/hilltop_article_1.txt | https://thehilltoponline.com/2024/11/25/students-frustrated-over-class-registration-delays-for-spring-semester/ |
| 9 | Unassigned professors/classrooms | The Hilltop | data/hilltop_article_2.txt | https://thehilltoponline.com/2024/08/26/bisonhub-sparks-confusion-amid-the-first-week-of-classes/ |
| 10 | Enrollment growth and staffing | The Hilltop | data/hilltop_article_3.txt | https://thehilltoponline.com/2023/02/27/enrollment-increase-puts-strain-on-students-teachers-in-college-of-arts-and-sciences/ |

John Harris (English) is deliberately included as a non-CS control case, and the official
EECS directory is deliberately included as an opinion-free factual baseline — it lets the
system confirm whether a professor a student asks about is currently listed in the
department.

---

## Architecture

```
Source Documents (10 .txt files)
        ↓
Document Ingestion / Cleaning        (src/ingest.py — type detection + whitespace normalization)
        ↓
Chunking                              (src/ingest.py — structure-aware, per document type)
        ↓
Embeddings                            (sentence-transformers, all-MiniLM-L6-v2)
        ↓
ChromaDB Vector Store                 (src/vector_store.py — persistent, cosine space)
        ↓
Semantic Retrieval (top-5)            (src/retrieve.py)
        ↓
Groq LLM                              (src/generate.py — openai/gpt-oss-120b, temperature 0)
        ↓
Grounded Answer + Sources             (source list built from chunk metadata, not from the LLM)
        ↓
Gradio Interface                      (src/app.py)
```

---

## Ingestion Pipeline

The ingester reads each `.txt` file, detects the document type from its headings (falling
back to the filename), and applies type-specific parsing. `src/ingest.py` then validates
every chunk before anything is embedded, and raises rather than silently indexing bad data:
it asserts that no chunk is empty, that every review chunk contains exactly one `Review N`
heading (so no review was split or merged), that every review chunk still names its
professor, that every directory chunk still names its faculty member, and that the directory
was not collapsed into a single chunk.

**A note on cleaning:** the source `.txt` files were manually transcribed from
RateMyProfessors and The Hilltop into a structured plain-text format, so navigation text,
ads, cookie banners, and HTML markup were removed at collection time rather than in code.
RateMyProfessors is JavaScript-rendered and blocks scripted requests, which is why manual
transcription was necessary. That is why the ingester only needs whitespace normalization and
type-specific structural parsing rather than HTML stripping — the cleaning step is real, it
just happened upstream of the code.

---

## Chunking Strategy

The chunk size is deliberately different per document type, because the three document types
have genuinely different structures.

**Chunk size:**

| Document type | Chunk unit | Resulting size | Chunks |
|---|---|---|---|
| RateMyProfessors reviews | one review per chunk | ~60–110 words | 24 |
| The Hilltop articles | paragraph groups, target 300 tokens | ~190–230 words | 3 |
| EECS faculty directory | one faculty entry per chunk | ~15–25 words | 21 |

**Overlap:**

- RateMyProfessors reviews: **no overlap.** A single review is already a complete, bounded
  opinion, so there is no boundary to bridge.
- The Hilltop articles: **50-token overlap**, applied between paragraph groups when an
  article exceeds the 300-token target.
- EECS directory: **no overlap.** Each entry is an independent record.

**Why these choices fit the documents:** a RateMyProfessors review is typically 1–3
sentences and self-contained — splitting one would separate a complaint from the reason
behind it ("exams mirror the homework" from "with different numbers"), and merging several
would blend contradictory opinions into one averaged-out embedding that matches no specific
query well. So the review *is* the natural chunk boundary, and a fixed character count would
cut across it arbitrarily. Because a review on its own says "he" and never names the
professor, each review chunk gets a normalized header block prepended (professor,
department, source URL, aggregate stats) so it remains interpretable in isolation. The
Hilltop articles are the opposite shape: long-form reporting where one point — a student's
complaint and the administrator's response to it — routinely spans multiple paragraphs, so
300 tokens is large enough to hold a claim together with its response, and the 50-token
overlap keeps a claim/response pair from being severed at a boundary. The directory is
structured records rather than prose, so splitting an entry further would produce a bare
email address with no name attached.

**Honest limitation:** the 300-token/50-token overlap path is implemented in
`chunk_paragraphs_with_overlap()` but **never actually fires on the current corpus**. All
three Hilltop articles are 192–230 words, so each falls under the 300-token target and
returns as a single chunk. Zero of the 47 chunks in the live index use overlap. The code path
is correct and tested, but the overlap strategy is currently unexercised — if I added a
longer article, or lowered the target, it would engage. I chose to report this rather than
describe overlap as if it were doing work.

**Final chunk count: 47** (24 review + 21 directory + 3 article). This sits just under the
assignment's 50-chunk guideline, which is a direct consequence of keeping each review and
each directory entry intact instead of splitting them into smaller fragments. I judged
faithful chunk boundaries to be worth more than hitting the count, and the retrieval results
below support that: the two questions that retrieve cleanly (distances 0.40–0.47) do so
because the matching chunk is exactly one complete review or one complete article.

---

## Sample Chunks

### Chunk 1
Source document: professor_2.txt

```text
Professor: Jiang Li
Department: Computer Science
Source: RateMyProfessors - https://www.ratemyprofessors.com/professor/2323879 (also mirrored on Coursicle)
Aggregate stats at time of collection: 1.6/5 overall quality, 16% would take again, 25 ratings, 4.7 difficulty

Review 1
Course: CSCI 170 / CSCI 200 (per Coursicle listing)
Rating context: Negative
Text: Describes the class as very hard, with online homework as the worst part - questions not drawn from any textbook, and single assignments reportedly taking up to 8 hours. States that understanding the material effectively requires going to him directly, though he does respond to email quickly. Notes exams mirror the homework format with different numbers, and that MIPS projects are graded by an automated script.
```

### Chunk 2
Source document: professor_1.txt

```text
Professor: Jeremy Blackstone
Department: Computer Science / Electrical Engineering and Computer Science
Source: RateMyProfessors - https://www.ratemyprofessors.com/professor/2640220
Aggregate stats at time of collection: 1.8/5 overall quality, 91% would take again, 21 ratings, 2.5 difficulty

Review 2
Course: Not specified
Rating context: Positive
Text: Calls him the best computer science professor the reviewer has had, saying he genuinely wants students to learn and sets them up for their career beyond Howard. States they couldn't ask for a better professor. Tags: participation matters, extra credit, clear grading criteria.
```

### Chunk 3
Source document: hilltop_article_1.txt

```text
Source Type: Student newspaper article (The Hilltop)
Title: Students Frustrated Over Class Registration Delays for Spring Semester
Source: https://thehilltoponline.com/2024/11/25/students-frustrated-over-class-registration-delays-for-spring-semester/
Date: November 25, 2024

Summary of reported information: A senior computer science major, Joshua Wallington, described significant stress from the Spring registration process, saying it has become difficult to register for classes he needs to graduate. Students reported having to continuously refresh the registration website to catch newly added course sections, since they receive no notification when new seats open.

Reinah McNeil, a senior broadcast journalism major and history minor, also reported frustration with the registration process and the added stress of a potentially delayed graduation because of it. She asked for clearer communication from the administration about registration to help students avoid these issues.

Courtney Robinson, an honors biology advisor, professor, and department chair, was interviewed to provide insight into the underlying causes of the registration issues from the faculty/administrative side.

Relevance to this project: This article documents a structural, university-wide problem (not tied to one professor) that directly affects whether students can even get into the courses they need - a key piece of context for a "course and professor guide."
```

### Chunk 4
Source document: professor_3.txt

```text
Professor: Gloria Washington
Department: Computer Science
Source: RateMyProfessors - https://www.ratemyprofessors.com/professor/2084505 (also mirrored on Coursicle)
Aggregate stats at time of collection: 2.7/5 overall quality, 42% would take again, 18 ratings, 3.7 difficulty. Top tags include: tough grader, group projects, lots of homework, participation matters, beware of pop quizzes.

Review 1
Course: Not specified (Coursicle-sourced)
Rating context: Negative
Text: Reports that her quizzes and tests sometimes contain mistakes, or questions where multiple answers could reasonably be correct, but she marks students wrong if the answer doesn't match her exact intended interpretation. States students often have to argue for points, and whether they receive them can depend on the day. Warns that skipping class or offending her makes this worse.
```

### Chunk 5
Source document: faculty_directory_eecs.txt

```text
Source: Howard University EECS faculty directory (https://cea.howard.edu/academics/departments/electrical-engineering-and-computer-science/people-eecs)
Department: Electrical Engineering and Computer Science, College of Engineering and Architecture (CEA)
Faculty: Jeremy Blackstone
jeremy.m.blackstone@howard.edu
```

Chunks 1, 2 and 4 show the review-per-chunk strategy: each is one complete student opinion
with its professor header re-attached. Chunk 3 shows an entire Hilltop article as one chunk.
Chunk 5 shows the smallest chunk type in the corpus — a single directory entry — which is
readable on its own but, as the failure analysis below explains, carries very little semantic
signal relative to its boilerplate header.

---

## Embedding Model

**Model used:** `all-MiniLM-L6-v2` via `sentence-transformers`, with embeddings normalized at
encode time and ChromaDB configured for cosine space (`hnsw:space: cosine`). It runs locally,
needs no API key, and has no rate limits, which fits a 47-chunk corpus where the whole index
rebuilds in seconds.

**Production tradeoff reflection:** for this small English-language corpus, running
embeddings locally keeps per-query cost at zero, avoids sending document text to an external
embedding API, and keeps the setup reproducible offline. If I were deploying this for real
users and cost were not a constraint, the factors I would weigh are:

- **Accuracy on domain-specific text.** This matters most here, and my evaluation shows why:
  MiniLM's 384 dimensions struggle to keep proper nouns distinct from surrounding
  boilerplate, which is the direct cause of my documented failure case. A larger model with
  stronger lexical sensitivity would likely fix Questions 2 and 4 outright.
- **Context length.** Less pressing for me than usual, since my largest chunk is ~230 words
  and MiniLM's 256-token window is only marginally binding. It would matter immediately if I
  moved to whole-article chunks.
- **Local vs. API latency and cost.** Local inference costs nothing per query but pins CPU
  and adds model load time on cold start; an API adds per-token cost, network dependence,
  and a data-transfer boundary — a real consideration given that this corpus contains named
  students and named faculty from published sources.
- **Multilingual support.** Not a priority for this corpus, which is entirely English. I
  would revisit it if the domain expanded to international-student communities.

Retrieval-quality evidence for the accuracy point is in the retrieval tests below, which
report real cosine distances rather than an impression.

---

## Retrieval Test Results

Generated by `python eval_dump.py`; full output including every retrieved chunk is committed
in [eval_output.md](eval_output.md). Distances are cosine distances, so lower is better.

### Query 1 — retrieval works
`What do students say about Jiang Li's grading and exams?`

| Rank | Source file | Distance |
|---|---|---|
| 1 | professor_2.txt | 0.416311 |
| 2 | professor_2.txt | 0.418871 |
| 3 | professor_2.txt | 0.432026 |
| 4 | professor_2.txt | 0.451942 |
| 5 | professor_4.txt | 0.472539 |

**Why these chunks are relevant:** the top four are all Jiang Li reviews, and each one
addresses the exact two things the query asks about. Rank 1 and 2 cover grading — GPA impact,
no extra credit, unilateral cheating decisions, having to "interview" to justify a project
grade. Rank 3 covers exams directly: "exams mirror the homework format with different
numbers." Rank 4 adds that homework outweighs exams in the final grade and that lectures do
not cover what is tested. Together they answer both halves of the question from the correct
professor's file, which is why this is the cleanest result in the set. Rank 5 is a Noha
Hazzazi review — wrong professor, but it is a CS grading complaint, so it is semantically
adjacent rather than random.

Verbatim top 3:

#### Chunk 1
Source file: professor_2.txt

```text
Professor: Jiang Li
Department: Computer Science
Source: RateMyProfessors - https://www.ratemyprofessors.com/professor/2323879 (also mirrored on Coursicle)
Aggregate stats at time of collection: 1.6/5 overall quality, 16% would take again, 25 ratings, 4.7 difficulty

Review 5
Course: Not specified
Rating context: Strongly negative
Text: Advises against taking the class, saying the professor "drains your GPA," does not care about students, and offers no extra credit. Claims he makes unilateral decisions about whether a student cheated and requires students to "interview" to justify a project grade. Recommends waiting for another professor's section instead.
```

#### Chunk 2
Source file: professor_2.txt

```text
Professor: Jiang Li
Department: Computer Science
Source: RateMyProfessors - https://www.ratemyprofessors.com/professor/2323879 (also mirrored on Coursicle)
Aggregate stats at time of collection: 1.6/5 overall quality, 16% would take again, 25 ratings, 4.7 difficulty

Review 6
Course: Not specified
Rating context: Strongly negative
Text: Calls him one of the worst professors the reviewer has had, saying he does not teach or explain concepts in depth, and refuses to clarify further when asked because students "should just get it." Reports that he ridicules students who don't understand and accuses students of cheating on projects if their understanding isn't judged sufficient.
```

#### Chunk 3
Source file: professor_2.txt

```text
Professor: Jiang Li
Department: Computer Science
Source: RateMyProfessors - https://www.ratemyprofessors.com/professor/2323879 (also mirrored on Coursicle)
Aggregate stats at time of collection: 1.6/5 overall quality, 16% would take again, 25 ratings, 4.7 difficulty

Review 1
Course: CSCI 170 / CSCI 200 (per Coursicle listing)
Rating context: Negative
Text: Describes the class as very hard, with online homework as the worst part - questions not drawn from any textbook, and single assignments reportedly taking up to 8 hours. States that understanding the material effectively requires going to him directly, though he does respond to email quickly. Notes exams mirror the homework format with different numbers, and that MIPS projects are graded by an automated script.
```

### Query 2 — retrieval fails
`What do students say about Jeremy Blackstone?`

| Rank | Source file | Distance |
|---|---|---|
| 1 | professor_1.txt | 0.607219 |
| 2 | professor_2.txt | 0.620430 |
| 3 | professor_6.txt | 0.625212 |
| 4 | professor_6.txt | 0.626040 |
| 5 | professor_6.txt | 0.627629 |

**Why these chunks are (and are not) relevant:** only rank 1 is actually relevant — it is a
Jeremy Blackstone review, and it is on-topic in that it is a general assessment of him, which
is what the query asked for. Ranks 2 through 5 are **not** relevant: rank 2 is Jiang Li and
ranks 3–5 are John Harris, an English professor. The revealing detail is the distance spread
— 0.607 to 0.628, a range of only 0.02. The correct professor is barely distinguished from
three chunks about a completely different person in a different department. Note also that
`professor_1.txt` contains **three** Blackstone reviews and only one of them was retrieved,
so this is a recall failure as well as a precision failure. This is the failure case analyzed
in detail below.

Verbatim top 3:

#### Chunk 1
Source file: professor_1.txt

```text
Professor: Jeremy Blackstone
Department: Computer Science / Electrical Engineering and Computer Science
Source: RateMyProfessors - https://www.ratemyprofessors.com/professor/2640220
Aggregate stats at time of collection: 1.8/5 overall quality, 91% would take again, 21 ratings, 2.5 difficulty

Review 2
Course: Not specified
Rating context: Positive
Text: Calls him the best computer science professor the reviewer has had, saying he genuinely wants students to learn and sets them up for their career beyond Howard. States they couldn't ask for a better professor. Tags: participation matters, extra credit, clear grading criteria.
```

#### Chunk 2
Source file: professor_2.txt

```text
Professor: Jiang Li
Department: Computer Science
Source: RateMyProfessors - https://www.ratemyprofessors.com/professor/2323879 (also mirrored on Coursicle)
Aggregate stats at time of collection: 1.6/5 overall quality, 16% would take again, 25 ratings, 4.7 difficulty

Review 6
Course: Not specified
Rating context: Strongly negative
Text: Calls him one of the worst professors the reviewer has had, saying he does not teach or explain concepts in depth, and refuses to clarify further when asked because students "should just get it." Reports that he ridicules students who don't understand and accuses students of cheating on projects if their understanding isn't judged sufficient.
```

#### Chunk 3
Source file: professor_6.txt

```text
Professor: John Harris
Department: English
Source: RateMyProfessors - https://www.ratemyprofessors.com/professor/2434383 (also mirrored at ratemyprofessors.com/professor?tid=2434383)
Aggregate stats at time of collection: 4.8/5 overall quality, 100% would take again, 19 ratings, 2.0 difficulty. Top tags include: caring, gives good feedback, clear grading criteria, respected, amazing lectures.

Review 6
Course: Not specified (pandemic-era semester)
Rating context: Positive
Text: Describes him as one of the more courteous professors during the pandemic period, saying the class was relatively useful and not too hard. Calls him a fair grader who was adaptable in helping students, noting that class meetings were shortened during that period.
```

### Query 3 — retrieval works
`What problems have students experienced with course registration at Howard?`

| Rank | Source file | Distance |
|---|---|---|
| 1 | hilltop_article_1.txt | 0.403237 |
| 2 | hilltop_article_3.txt | 0.459978 |
| 3 | hilltop_article_2.txt | 0.495717 |
| 4 | professor_4.txt | 0.550948 |
| 5 | professor_3.txt | 0.620523 |

**Why these chunks are relevant:** the top three are all three Hilltop articles, and they
cover three distinct causes of the same problem, which is exactly what a "what problems"
question needs. Rank 1 is the registration-delay article — refreshing the site for new
sections, no notification when seats open, graduation timing. Rank 2 is the enrollment-strain
article, which supplies the *cause* on the advising side: unresponsive advisors and being
redirected to an advisor no longer employed by the university. Rank 3 is the unassigned
professors/classrooms article, which supplies a structural cause on the data-entry side. The
clean separation of the distance scores here (0.40 → 0.46 → 0.50, then a jump to 0.55) shows
the retriever correctly identifying the article corpus as the relevant subset and the
professor reviews as noise. Ranks 4 and 5 are professor reviews and are not real evidence for
this question.

**Threshold check:** the assignment's checkpoint asks for top distances below 0.5. Queries 1
and 3 clear it (0.416 and 0.403). Query 2 does not — its best is 0.607219 — and neither does
Question 4 in the evaluation report, whose best is 0.620219. Question 5 is the out-of-scope
Georgetown query, whose best is 0.514058, and in that case a weak match is the *correct*
outcome, since nothing in the corpus should match. I am reporting the two genuine misses
rather than only the queries that pass.

---

## Grounded Generation

Generation uses Groq with the model string `openai/gpt-oss-120b` at `temperature=0`.

Grounding is enforced in three places, not just by asking the model nicely:

**1. The system prompt** ([src/generate.py](src/generate.py)) states the constraint as a hard
rule and supplies the exact refusal sentence:

```text
You are a grounded question-answering assistant for Howard University course and professor documents.

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
```

**2. Structurally, the model only ever sees retrieved text.** `build_retrieved_context()`
assembles the prompt from the retrieved chunks alone — each labelled with its chunk ID,
source description, and metadata — and the user message repeats the constraint. There is no
path by which un-retrieved document text or conversation history reaches the model.

**3. Source attribution is computed, not requested.** This is the part that matters most for
trustworthiness. The source list is built in Python by `build_sources_text()` from the
retrieved chunks' `source_file` and `source` metadata, so it cannot be hallucinated. When the
model cites chunk IDs inline, `extract_cited_chunk_ids()` parses them and narrows the source
list to *only the chunks actually cited* — so a Blackstone answer lists `professor_1.txt`
alone rather than all five retrieved files. Chunk IDs that the model invents are dropped,
because the citation is looked up in the retrieved set and a miss is discarded. If the answer
is the refusal sentence, `is_refusal()` replaces the list with an explicit "None" line so a
refusal can never appear to be supported by sources.

---

## Example Responses

Both examples show source attribution in the output, produced by the pipeline rather than by
the model.

### Example 1 — Jiang Li (grounded, multiple chunks cited)

```text
Question: What do students say about Jiang Li's grading and exams?

Answer:
Students' comments about Jiang Li's grading and exams are consistently negative.

* One reviewer says the professor "drains your GPA," offers no extra-credit opportunities, and can make unilateral decisions about cheating - even requiring a student to "interview" to justify a project grade【professor_2::review_5】.
* Another reviewer calls him "one of the worst professors," noting that he refuses to clarify concepts and accuses students of cheating when their understanding seems insufficient【professor_2::review_6】.

Regarding the exams themselves:

* A student describes the exams as essentially the same format as the online homework (same style of questions, just different numbers), and notes that the homework assignments can take many hours to complete【professor_2::review_1】.
* Another reviewer points out that homework counts for a larger portion of the final grade than the exams, and that lecture content often does not cover what is actually tested【professor_2::review_7】.

Overall, students report that Jiang Li's grading is perceived as harsh and that the exams closely mirror the difficult homework assignments, with a heavy emphasis on homework in the final grade.

Sources:
1. professor_2.txt — RateMyProfessors (Jiang Li, Computer Science)
```

Note that the source list contains only `professor_2.txt`, even though a `professor_4.txt`
chunk was also retrieved at rank 5 — the citation filter removed the uncited file.

### Example 2 — Jeremy Blackstone (grounded, single chunk cited)

```text
Question: What do students say about Jeremy Blackstone?

Answer:
Students who have reviewed Jeremy Blackstone describe him very positively. One reviewer calls him "the best computer-science professor" they have had, saying he "genuinely wants students to learn" and "sets them up for their career beyond Howard." The reviewer adds that they "couldn't ask for a better professor." The review also notes that his class emphasizes participation, offers extra credit, and has clear grading criteria【professor_1::review_2】.

Sources:
1. professor_1.txt — RateMyProfessors (Jeremy Blackstone, Computer Science / Electrical Engineering and Computer Science)
```

This answer is correctly grounded — every claim traces to the one Blackstone chunk that was
retrieved — but it is **incomplete**, because retrieval never surfaced the negative Blackstone
review that exists in the same file. Good grounding on bad retrieval still produces a
misleading answer. That is the failure case below.

### Example 3 — out-of-scope query (refusal)

```text
Question: What do students say about the Computer Science professors at Georgetown University?

Answer:
I don't have enough information in the provided sources to answer that question.

Sources:
None — the retrieved sources do not contain enough information to answer the question.
```

The corpus contains nothing about Georgetown, and retrieval still returned five chunks — its
best at distance 0.514058 — because a vector search always returns its nearest neighbours no
matter how far away they are. The refusal is therefore doing real work: the model was handed
five Howard professor-review chunks and declined to repurpose them into a plausible-sounding
answer about a different university.

---

## Query Interface

A Gradio web app, launched with `python src/app.py` and served at `http://localhost:7860`.

**Input fields:**

| Field | Type | Purpose |
|---|---|---|
| `Question` | multi-line textbox (3 lines) | The plain-language question. Placeholder text reads "Ask about a professor, article, or Howard registration issue." |
| `Submit` | button | Runs the query. Pressing Enter in the question box does the same thing. |

**Output fields:**

| Field | Type | Purpose |
|---|---|---|
| `Answer` | textbox (8 lines), read-back | The grounded answer, with inline `【chunk_id】` citations |
| `Sources` | textbox (6 lines), read-back | The computed source list — filename plus source type, professor, or article title |

A command-line interface is also available for the same pipeline via
`python src/generate.py "your question"`, which prints the question, answer, and sources.

**Sample interaction transcript** (one complete query and response):

```text
$ python src/app.py
* Running on local URL:  http://127.0.0.1:7860

--- in the browser ---

Question:  What problems have students experienced with course registration at Howard?

[Submit]

Answer:
Students have reported several recurring problems with Howard's course-registration process:

* Delays and difficulty securing needed seats - Senior Joshua Wallington said the spring
  registration was "significantly stressful" because it had become hard to enroll in the
  classes he needs to graduate. Many students said they have to keep refreshing the
  registration website and receive no notification when new seats open, making it easy to
  miss openings【hilltop_article_1::chunk_1】.
* Unclear communication and fear of delayed graduation - Senior broadcast-journalism major
  Reinah McNeil expressed frustration that the process was poorly communicated, adding
  stress and the possibility of a delayed graduation. She called for clearer information
  from the administration【hilltop_article_1::chunk_1】.
* Advisor-related obstacles - In a separate article, a student named Fleming described how a
  lack of response from faculty advisors, and being redirected to an advisor who was no
  longer employed at Howard, caused her registration to take "so long."
  【hilltop_article_3::chunk_1】
* Impact of rising enrollment - The College of Arts and Sciences has seen enrollment rise to
  nearly 4,000 students, which has strained capacity, led to larger class sizes, and made it
  harder for students to find available seats in required courses【hilltop_article_3::chunk_1】.

Sources:
1. hilltop_article_1.txt — The Hilltop (Students Frustrated Over Class Registration Delays for Spring Semester)
2. hilltop_article_3.txt — The Hilltop (Enrollment Increase Puts Strain On Students, Teachers in College of Arts and Sciences)
```

---

## Evaluation Report

All five questions come from the Evaluation Plan in [planning.md](planning.md). Full
retrieved chunks and raw generated answers for every question are committed in
[eval_output.md](eval_output.md), regenerable with `python eval_dump.py`.

| # | Question | Expected answer | System response | Retrieval quality | Accuracy judgment |
|---|---|---|---|---|---|
| 1 | What do students say about Jiang Li's grading and exams? | Grading is commonly described as unclear or difficult, several reviews say lectures do not match the homework or exams, and some students recommend against taking the course with him. | Reported grading as harsh — "drains your GPA," no extra credit, unilateral cheating decisions; exams mirror the homework format with different numbers; homework outweighs exams in the final grade and lectures do not cover what is tested. Cited four separate `professor_2` review chunks. | Relevant (4 of 5 chunks from the correct file, best distance 0.416) | **accurate** |
| 2 | What do students say about Jeremy Blackstone? | Reviews are mostly positive and describe him as engaging and career-focused. There is also at least one negative comment about slow grading. | Described him as very positive and career-focused, citing one review. **Omitted the negative review entirely** — no mention of slow grading, disorganization, or the wrong final exam being posted. | Off-target (1 of 5 chunks relevant, best distance 0.607) | **partially accurate** |
| 3 | What problems have students experienced with course registration at Howard? | Students report problems with BisonHub, including incorrect or incomplete course information, professors or classrooms not being assigned, and students not always being notified when new sections become available. | Reported delays securing seats, no notification when seats open, unclear communication and delayed-graduation risk, unresponsive advisors including one no longer employed, and enrollment growth straining capacity. **Did not mention BisonHub or unassigned professors/classrooms**, though the article covering those ranked 3rd. | Relevant (3 of 5 chunks from the correct files, best distance 0.403) | **partially accurate** |
| 4 | Do students have consistent opinions about Gloria Washington? | No. The reviews are mixed. Some students describe her courses as difficult, while others describe her as fair and mention useful extra credit opportunities. | "The student reviews of Professor Gloria Washington are mixed rather than consistent." Cited the negative review (exact-answer grading, arguing for points) and the positive review (great teacher overall, predictable pop quizzes, extra credit), and explicitly stated the sentiment is not uniform. | Partially relevant (2 of 5 chunks relevant, and the **wrong professor ranked first** at 0.620) | **accurate** |
| 5 | What do students say about the Computer Science professors at Georgetown University? | The system should say that the document collection does not contain enough information to answer this question. | "I don't have enough information in the provided sources to answer that question." Source list explicitly "None." | Correctly off-target — nothing in the corpus is relevant, best distance 0.514 | **accurate** |

**Summary: 3 accurate, 2 partially accurate, 0 inaccurate.**

Two notes on the judgments, because the retrieval quality and the accuracy judgment come
apart in opposite directions in two places:

- **Question 3 is graded down against its own spec.** The planning.md expected answer
  specifically names BisonHub and unassigned professors/classrooms. The system answered
  correctly about registration but produced neither of those specifics, even though
  `hilltop_article_2.txt` — the BisonHub article — was retrieved at rank 3. The generator
  drew its four bullets from ranks 1 and 2 and effectively ignored rank 3. Judged strictly
  against the pre-written expected answer, that is partially accurate, not accurate.
- **Question 4 is accurate despite failing retrieval.** The top-ranked chunk was a Noha
  Hazzazi review from `professor_4.txt` — the wrong professor entirely. The correct Gloria
  Washington chunks ranked 2nd and 3rd. The answer is right only because the generator
  ignored the irrelevant top hit and used ranks 2 and 3. Correct generation masked a real
  retrieval failure here, which is why the retrieval-quality column is reported separately
  from the accuracy column.

---

## Failure Case Analysis

**Question that failed:** Question 2 — "What do students say about Jeremy Blackstone?"

**What the system returned:** a uniformly positive summary sourced from a single review
chunk (`professor_1::review_2`), correctly grounded and correctly cited, but describing
Blackstone as an unqualified success.

**What it should have returned:** `professor_1.txt` contains **three** Blackstone reviews, and
Review 3 is sharply negative — the reviewer opens by saying they are surprised by all the
positive reviews, reports that by finals week for seniors only one assignment had been
graded, calls the lecture slides "lazy ppts," and states the professor posted the wrong final
exam and then altered the questions without clearly telling students. A student relying on my
system would have been shown a materially misleading picture of this professor.

**Root cause, tied to a specific pipeline stage: the chunking stage, surfacing as a retrieval
failure.** This is not a hallucination and not a generation failure — the generator did the
right thing with what it was given. The cause is in how I built the chunks.

Every RateMyProfessors review chunk begins with the same four-line header block: professor,
department, source URL, and aggregate stats. That header is roughly 40–60 words, while the
review text it precedes is often only 40–80 words. So for a short review, **more than half
the embedded tokens are boilerplate**, and the boilerplate is structurally near-identical
across all 24 review chunks — same field names, same URL prefix, same "Aggregate stats at
time of collection" phrasing, same "N/5 overall quality, N% would take again" pattern. A
single averaged 384-dimension embedding cannot help but be pulled toward that shared
template, which compresses all 24 review chunks into a tight neighbourhood. The visible
symptom is the distance spread in Query 2: ranks 1 through 5 span 0.607 to 0.628, a range of
0.02, so the correct professor's review is separated from a chunk about an English professor
by almost nothing.

The irony is that I added the header block deliberately and for a good reason — a review that
says only "he" needs its professor's name attached to be interpretable in isolation, and
that fix worked. But I added the same block to *every* chunk, which made the discriminative
token ("Blackstone") a small fraction of each embedding instead of a prominent one. The fix
for standalone readability directly caused the retrieval failure.

The same mechanism explains the other two anomalies in the evaluation:

- **Question 4** (wrong professor ranked first at 0.620) is the identical effect — "Gloria
  Washington" is not weighted enough to beat a header-similar chunk about Noha Hazzazi.
- **The 21 faculty-directory chunks** are the extreme case. Each is ~15–25 words of content
  behind a two-line source/department header that is *byte-identical* across all 21. Those
  chunks are nearly indistinguishable from one another in embedding space, which is why
  directory entries almost never surface usefully despite making up 45% of the corpus.

**What I would change to fix it, in order of expected payoff:**

1. **Hybrid retrieval with BM25**, so an exact surname match can outrank a
   semantically-average header. This is the direct fix for a lexical failure and is
   implemented below as a stretch feature.
2. **Metadata filtering on `professor`**, so a query naming a professor can restrict the
   candidate set instead of hoping the embedding sorts it out. Also implemented below.
3. **Embed the review text alone and keep the header in metadata only**, so the boilerplate
   informs display and attribution without diluting the vector. This would change the chunk
   count and is a larger refactor.
4. **A cross-encoder reranker** over the top 20 candidates, which would judge query/chunk
   relevance jointly rather than through a single averaged vector.

---

## Spec Reflection

**One way the spec helped me during implementation:** the Chunking Strategy section forced
me to commit to *per-document-type* chunking before I wrote any code, and that decision
turned out to carry the whole pipeline. Because the plan already said "one review per chunk,
no overlap" for RateMyProfessors and "300 tokens with 50-token overlap" for The Hilltop, I
built `ingest.py` around a type-detection dispatch from the start rather than writing one
generic splitter and retrofitting special cases into it. That structure is also what made the
validation step possible: since the spec defined what a correct chunk *is* for each type, I
could write `validate_chunks()` to assert exactly one `Review N` heading per review chunk and
a present professor name in every chunk, and have it raise before anything reaches the
embedder. I would not have known what to assert without having written the spec first.

**One way my implementation diverged from the spec, and why:** the divergence I most need to
own is that **I rewrote the expected answers between planning.md and my first draft of this
README**, after seeing what the system produced. The clearest case is Question 3: planning.md
specifies BisonHub and unassigned professors/classrooms as the expected answer, and my
earlier README quietly replaced that with a description matching what the system actually
said, then marked the result "accurate." That is grading myself against my own output rather
than against my spec, which defeats the point of writing the spec first. This version
restores the planning.md expected answers verbatim in the evaluation table and re-judges
Question 3 as **partially accurate** against the original standard, which is the honest
result.

Two smaller divergences, both consequences of holding to the spec rather than departing from
it: the corpus came out at **47 chunks**, just under the assignment's 50-chunk guideline,
because one-review-per-chunk and one-entry-per-chunk produce whatever count the documents
produce — I decided faithful boundaries were worth more than padding the number. And the
**50-token overlap I specified never executes**, because all three Hilltop articles came in
under the 300-token target; the code path exists and is correct, but the corpus never
triggers it, so the spec describes a mechanism the live system does not currently use.

---

## AI Usage

> The two instances below describe how I directed Claude during implementation. Both are tied
> to specific code that is in the repository.

**Instance 1 — the ingestion and chunking module (`src/ingest.py`)**

- *What I gave the AI:* the Documents and Chunking Strategy sections of my planning.md, plus
  the pipeline diagram, plus two actual sample files (`professor_2.txt` and
  `hilltop_article_1.txt`) so it could see the real `---` review delimiters and header format
  rather than guessing at my structure. My instruction was to implement three separate
  parsers behind one type-detecting entry point, not one generic splitter with flags.
- *What it produced:* a working three-way parser, but with two things I did not accept. First,
  it proposed detecting document type from the filename prefix alone (`professor_`,
  `hilltop_article_`). Second, it produced no verification of its own output — it trusted the
  regex split.
- *What I changed or overrode:* I made type detection read the file's **content** first
  (`^Professor:`, `^Source Type: Official Howard University department page`, `^Title:` plus a
  "The Hilltop" match) and kept the filename check only as a fallback, because filename-based
  detection would silently mis-parse any document I renamed. I also added
  `validate_chunks()`, which raises before embedding if any chunk is empty, if a review chunk
  contains anything other than exactly one `Review N` heading, if a review or directory chunk
  has lost its professor name, or if the directory collapsed to a single chunk. That check is
  what let me trust the 47-chunk count instead of eyeballing it. I additionally added the
  `ARTICLE_MIN_TAIL_TOKENS = 100` tail-merge rule, which was not in my plan, after reasoning
  that a 20-word orphan paragraph as its own chunk would be worse than a slightly oversized
  final chunk.

**Instance 2 — source attribution in `src/generate.py`**

- *What I gave the AI:* my grounding requirement (answer from retrieved context only, cite
  sources) and the desired output shape of answer plus source list.
- *What it produced:* a version that asked the model to write its own source list at the end
  of the answer, and parsed that text back out.
- *What I changed or overrode:* I rejected that design, because a hallucinated source line is
  worse than no source line — the whole point of citations is that they can be trusted. I
  restructured it so the source list is **computed in Python** by `build_sources_text()` from
  the retrieved chunks' metadata, and the model's only citation job is to emit chunk IDs
  inline. `extract_cited_chunk_ids()` then looks each ID up in the retrieved set and narrows
  the list to the cited files, silently dropping any ID the model invented. I also widened
  that regex to accept `【...】` full-width brackets after observing that
  `openai/gpt-oss-120b` emits those instead of the ASCII `[...]` I had asked for — the
  citations were being parsed as zero matches until I handled the unicode form.
- *A later correction of my own:* the refusal branch originally tested
  `if INSUFFICIENT_INFO_RESPONSE in answer_text`, a substring check. A code review pointed out
  that a partial answer beginning "I don't have enough information ... about X, but reviewers
  do say Y" would match and wipe a legitimate source list. I replaced it with `is_refusal()`,
  which only matches when the refusal sentence is the entire answer.

**Where I did not use AI:** planning.md is my own work, per the assignment's guardrail. I
also wrote the failure-case root-cause analysis myself, from reading the distance spreads in
`eval_output.md` — the boilerplate-dilution explanation came from noticing that the top five
Query 2 results span only 0.02, then going back to look at what those chunks have in common.
