from __future__ import annotations

import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gradio as gr

from src.generate import generate_answer


def answer_question(question: str) -> tuple[str, str]:
    result = generate_answer(question)
    return result["answer"], result["sources"]


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Howard Course and Professor Guide") as demo:
        gr.Markdown("# Howard Course and Professor Guide\nAsk a question and get a grounded answer from the retrieved Howard sources.")
        question_box = gr.Textbox(label="Question", placeholder="Ask about a professor, article, or Howard registration issue.", lines=3)
        submit_button = gr.Button("Submit")
        answer_box = gr.Textbox(label="Answer", lines=8)
        sources_box = gr.Textbox(label="Sources", lines=6)

        submit_button.click(answer_question, inputs=question_box, outputs=[answer_box, sources_box])
        question_box.submit(answer_question, inputs=question_box, outputs=[answer_box, sources_box])

    return demo


def main() -> None:
    app = build_app()
    app.launch()


if __name__ == "__main__":
    main()