# Project 1 Planning: The Unofficial Guide

> Write this document before you write any pipeline code.
> Your spec and architecture diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Update the Retrieval Approach and Chunking Strategy sections if you change your approach during implementation.
> Update this file before starting any stretch features.

---

## Domain

<!-- What domain did you choose? Why is this knowledge valuable and hard to find through official channels?  -->
I chose Howard University Course and Professor Guide. This knowledge is valuable and hard to find officially because Howard's catalog and department pages only describe what a course covers, and not how the professor teaches it. The information is instead scattered across various sources and a new/transfer student would not know where to look.

---

## Documents

<!-- List your specific sources: URLs, subreddit names, forum threads, or file descriptions.
     Aim for at least 10 sources that together cover different subtopics or perspectives within your domain. -->

| # | Source | Description | URL or location |
|---|--------|-------------|-----------------|
| 1 | RateMyProfessors| Jeremy Blackstone, Computer Science| https://www.ratemyprofessors.com/professor/2640220|
| 2 | RateMyProfessors| Jiang Li, Computer Science| https://www.ratemyprofessors.com/professor/2323879|
| 3 | RateMyProfessors| Gloria Washington, Computer Science| https://www.ratemyprofessors.com/professor/2084505|
| 4 | RateMyProfessors| Noha Hazzazi, Computer Science| https://www.ratemyprofessors.com/professor/2418869|
| 5 | RateMyProfessors| Anamika Rupa, Computer Science| https://www.ratemyprofessors.com/professor/2976470|
| 6 | RateMyProfessors| John Harris, English (non-CS control case)| https://www.ratemyprofessors.com/professor/2434383|
| 7 | Howard University CEA| Official EECS faculty directory (baseline, no opinion)| https://cea.howard.edu/academics/departments/electrical-engineering-and-computer-science/people-eecs|
| 8 | The Hilltop| Article on registration delays for Spring semester| https://thehilltoponline.com/2024/11/25/students-frustrated-over-class-registration-delays-for-spring-semester/|
| 9 | The Hilltop| Article on unassigned professors/classrooms at semester start| https://thehilltoponline.com/2024/08/26/bisonhub-sparks-confusion-amid-the-first-week-of-classes/|
| 10 | The Hilltop| Article on enrollment strain on COAS faculty| https://thehilltoponline.com/2023/02/27/enrollment-increase-puts-strain-on-students-teachers-in-college-of-arts-and-sciences/|

---

## Chunking Strategy

<!-- How will you split documents into chunks?
     State your chunk size (in tokens or characters), overlap size, and explain why those
     numbers fit the structure of your documents.
     A review-heavy corpus warrants different chunking than a long FAQ. -->

**Chunk size:** It depends on the type of document. For the Rate My Professor pages, each individual review would be its own chunk instead of using a fixed size. For the Hilltop articles, I would use chunks of around 300 tokens. For the EECS directory, I would keep each faculty entry as one small chunk.

**Overlap:** For the Rate My Professor reviews, no overlap is needed because each review is already a complete unit. For the Hilltop articles, I would use a 50-token overlap between chunks. The EECS directory entries would also have no overlap.

**Reasoning:** I would use different chunk sizes depending on the structure of the document. For Rate My Professor, a single review is already a complete opinion, usually around 1–3 sentences, so splitting it could separate a complaint from the explanation behind it. I would also add the professor’s name and department to each review so that the chunk still makes sense on its own. For the Hilltop articles, I would use around 300 tokens with 50-token overlap and try to break on paragraph boundaries when possible. These articles are longer and contain a lot of quotes, and one point, such as a student’s complaint and an administrator’s response, can span multiple paragraphs. The overlap helps prevent important information from being lost between chunks. For the EECS directory, I would keep each faculty entry together because it is structured information rather than regular prose, so splitting it further would not add much value.

---

## Retrieval Approach

<!-- Which embedding model are you using (e.g., all-MiniLM-L6-v2 via sentence-transformers)?
     How many chunks will you retrieve per query (top-k)?
     If you were deploying this for real users and cost wasn't a constraint, what tradeoffs
     would you weigh in choosing a different embedding model — context length, multilingual
     support, accuracy on domain-specific text, latency? -->

**Embedding model:** I will use all-MiniLM-L6-v2 through the sentence-transformers library. I chose it because the corpus is relatively small, and it is lightweight while still being good enough for semantic search. Each chunk will be converted into an embedding and stored in a vector index.

**Top-k:** I will start with a top-k of 5. This should retrieve enough reviews to capture different student opinions without giving the generation model too much unrelated information. I can adjust this after testing if important information is being missed or too many irrelevant chunks are being retrieved.

**Production tradeoff reflection:** If this were being deployed for real users and cost was not a constraint, I would consider a larger embedding model if testing showed that it improved retrieval accuracy. I would mainly compare accuracy, how well it handles domain-specific wording, context length, and latency. Since this project has a small English-language corpus, multilingual support would not be a major priority.

---

## Evaluation Plan

<!-- List your 5 test questions with their expected correct answers.
     Questions should be specific enough that you can judge whether the system's response
     is right or wrong. "What are good dining halls?" is too vague.
     "What do students say about wait times at [dining hall name] during lunch?" is testable. -->

| # | Question | Expected answer |
|---|----------|-----------------|
| 1 | What do students say about Jiang Li’s grading and exams?| Reviews commonly describe the grading as unclear or difficult to understand, and several reviews say the lectures do not match the homework or exams. Some students recommend against taking the course with him.|
| 2 | What do students say about Jeremy Blackstone?| Reviews are mostly positive and describe him as engaging and career-focused. There is also at least one negative comment about slow grading.|
| 3 | What problems have students experienced with course registration at Howard?| Students have reported problems with BisonHub, including incorrect or incomplete course information, professors or classrooms not being assigned, and students not always being notified when new sections become available.|
| 4 | Do students have consistent opinions about Gloria Washington?| No. The reviews are mixed. Some students describe her courses as difficult, while others describe her as fair and mention useful extra credit opportunities.|
| 5 | What do students say about the Computer Science professors at Georgetown University?| The system should say that the document collection does not contain enough information to answer this question.|

---

## Anticipated Challenges

<!-- What could go wrong? Name at least two specific risks with reasoning.
     Consider: noisy or inconsistent documents, missing source attribution, off-topic
     retrieval, chunks that split key information across boundaries. -->

1.     Students can have very different experiences with the same professor and a professor’s teaching style or a registration system can change over time, so the system may need to consider the date of the source when answering.

2.     Rate My Professor reviews are personal experiences, so the system needs to make it clear when something is based on student reports instead of presenting it as an objective fact.

---

## Architecture

<!-- Draw a diagram of your pipeline showing the five stages:
     Document Ingestion → Chunking → Embedding + Vector Store → Retrieval → Generation
     Label each stage with the tool or library you're using.
     You can use ASCII art, a Mermaid diagram, or embed a sketch as an image.
     You'll use this diagram as context when prompting AI tools to implement each stage. -->

```
Source Documents

       ↓

Document Ingestion / Cleaning

       ↓

Chunking

       ↓

Embeddings

       ↓

ChromaDB Vector Store

       ↓

User Question

       ↓

Semantic Retrieval (Top 5)

       ↓

Retrieved Context

       ↓

Groq LLM

       ↓

Grounded Answer + Sources

       ↓

Gradio Interface
```

---

## AI Tool Plan

<!-- For each part of the pipeline below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, which requirements)
     - What you expect it to produce
     - How you'll verify the output matches your spec

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Chunking Strategy section and ask it to implement chunk_text()
     with my specified chunk size and overlap" is a plan. -->

**Milestone 3 — Ingestion and chunking:**
I will use Claude to help implement the document ingestion and chunking functions. I will give it the Documents and Chunking Strategy sections of this file and ask it to implement separate handling for Rate My Professor reviews, Hilltop articles, and EECS directory entries. I will verify the output by checking the generated chunks to make sure reviews are not split, Hilltop chunks are close to 300 tokens with 50-token overlap, and directory entries remain together.

**Milestone 4 — Embedding and retrieval:**
I will use Claude to implement the embedding and retrieval pipeline using all-MiniLM-L6-v2 and a vector index. I will give it the Retrieval Approach section and require it to use cosine similarity and return the top 5 chunks for each query. I will test it using the evaluation questions and inspect the retrieved chunks to make sure they are relevant to the question.

**Milestone 5 — Generation and interface:**
I will use Claude to implement the generation step using openai/gpt-oss-120b. I will give it the Retrieval Approach, Evaluation Plan, and grounding requirements. The generated answer should only use the retrieved documents, identify conflicting opinions, and say when the collection does not contain enough information. I will verify the final answers against the expected answers in the evaluation table and manually inspect whether the responses are properly grounded in the retrieved sources.
