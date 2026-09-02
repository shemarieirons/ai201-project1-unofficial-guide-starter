from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gradio as gr

from src.generate import DEFAULT_METHOD, generate_answer
from src.vector_store import get_all_chunks

ANY_OPTION = "Any"


def filter_options() -> tuple[list[str], list[str]]:
    """Read the available filter values out of the stored chunk metadata."""
    sources = {ANY_OPTION}
    professors = {ANY_OPTION}
    for chunk in get_all_chunks():
        metadata = chunk["metadata"]
        if metadata.get("source"):
            sources.add(str(metadata["source"]))
        if metadata.get("professor"):
            professors.add(str(metadata["professor"]))
    return (
        [ANY_OPTION] + sorted(sources - {ANY_OPTION}),
        [ANY_OPTION] + sorted(professors - {ANY_OPTION}),
    )


def build_where(source: str, professor: str) -> dict[str, Any] | None:
    where: dict[str, Any] = {}
    if source and source != ANY_OPTION:
        where["source"] = source
    if professor and professor != ANY_OPTION:
        where["professor"] = professor
    return where or None


def format_retrieved(result: dict[str, Any]) -> str:
    """Show what retrieval actually returned, so the interface is inspectable in a demo."""
    lines: list[str] = []
    for chunk in result.get("chunks", []):
        distance = chunk.get("distance")
        distance_text = f"distance {distance:.4f}" if isinstance(distance, (int, float)) else "distance n/a"
        lines.append(f"{chunk['rank']}. {chunk['chunk_id']}  ({distance_text})")
    return "\n".join(lines) or "No chunks retrieved."


def answer_question(
    question: str,
    method: str,
    source: str,
    professor: str,
    use_memory: bool,
    history: list[tuple[str, str]] | None,
) -> tuple[str, str, str, str, list[tuple[str, str]]]:
    history = list(history or [])
    question = (question or "").strip()
    if not question:
        return "Enter a question first.", "", "", "", history

    result = generate_answer(
        question,
        method=method,
        where=build_where(source, professor),
        history=history if use_memory else None,
    )

    rewritten = result.get("search_question", question)
    if use_memory and rewritten != question:
        rewrite_note = f"Follow-up resolved to: {rewritten}"
    elif use_memory and history:
        rewrite_note = "Already standalone — used as written."
    else:
        rewrite_note = "Conversation memory off."

    history.append((question, result["answer"]))
    return result["answer"], result["sources"], format_retrieved(result), rewrite_note, history


def build_app() -> gr.Blocks:
    source_choices, professor_choices = filter_options()

    with gr.Blocks(title="Howard Course and Professor Guide") as demo:
        gr.Markdown(
            "# Howard Course and Professor Guide\n"
            "Ask a question and get an answer grounded only in the retrieved Howard sources."
        )

        history_state = gr.State([])

        with gr.Row():
            with gr.Column(scale=3):
                question_box = gr.Textbox(
                    label="Question",
                    placeholder="Ask about a professor, article, or Howard registration issue.",
                    lines=3,
                )
            with gr.Column(scale=2):
                method_radio = gr.Radio(
                    choices=["hybrid", "semantic", "bm25"],
                    value=DEFAULT_METHOD,
                    label="Retrieval method",
                    info="hybrid = BM25 + semantic fusion",
                )
                memory_checkbox = gr.Checkbox(
                    value=True,
                    label="Conversation memory",
                    info="Resolves follow-ups like 'Is he a hard grader?' before retrieval",
                )

        with gr.Row():
            source_dropdown = gr.Dropdown(
                choices=source_choices, value=ANY_OPTION, label="Filter by source"
            )
            professor_dropdown = gr.Dropdown(
                choices=professor_choices, value=ANY_OPTION, label="Filter by professor"
            )

        with gr.Row():
            submit_button = gr.Button("Ask", variant="primary")
            reset_button = gr.Button("New conversation")

        answer_box = gr.Textbox(label="Answer", lines=10)
        sources_box = gr.Textbox(label="Sources", lines=4)
        with gr.Accordion("Retrieval detail", open=False):
            retrieved_box = gr.Textbox(label="Retrieved chunks", lines=6)
            rewrite_box = gr.Textbox(label="Conversation memory", lines=2)

        inputs = [
            question_box,
            method_radio,
            source_dropdown,
            professor_dropdown,
            memory_checkbox,
            history_state,
        ]
        outputs = [answer_box, sources_box, retrieved_box, rewrite_box, history_state]

        submit_button.click(answer_question, inputs=inputs, outputs=outputs)
        question_box.submit(answer_question, inputs=inputs, outputs=outputs)
        reset_button.click(
            lambda: ("", "", "", "Conversation cleared.", []),
            outputs=outputs,
        )

    return demo


def main() -> None:
    build_app().launch()


if __name__ == "__main__":
    main()
