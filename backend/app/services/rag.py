"""
Retrieval-Augmented Generation (RAG) service for the lecture chatbot.

Pipeline: embed query -> retrieve top-k chunks -> build grounded context ->
call LLM with strict grounding instructions -> return answer + sources.

The system prompt explicitly forbids the model from inventing information
that isn't present in the retrieved context, and instructs it to say so
when the answer cannot be found.
"""
import time
from typing import Dict, List
from app.services.retrieval import retrieve_relevant_chunks
from app.services.llm_provider import generate, LLMError

NOT_FOUND_MESSAGE = "I could not find sufficient information about this in the uploaded lecture."

RAG_SYSTEM_PROMPT = (
    "You are LectureMind, an assistant that answers student questions strictly using the "
    "provided lecture transcript excerpts. Rules:\n"
    "1. Only use information present in the given CONTEXT. Do not use outside knowledge.\n"
    "2. If the CONTEXT does not contain enough information to answer, respond with exactly: "
    f"\"{NOT_FOUND_MESSAGE}\"\n"
    "3. Do not fabricate facts, numbers, or names that are not in the CONTEXT.\n"
    "4. Keep answers clear, concise and directly related to the question.\n"
    "5. When useful, you may briefly mention which part of the lecture supports the answer."
)


def _build_context(chunks: List[Dict]) -> str:
    parts = []
    for c in chunks:
        mm_start = f"{int(c['start'] // 60):02d}:{int(c['start'] % 60):02d}"
        mm_end = f"{int(c['end'] // 60):02d}:{int(c['end'] % 60):02d}"
        parts.append(f"[{mm_start} - {mm_end}] {c['text']}")
    return "\n\n".join(parts)


def answer_question(lecture_id: str, question: str, top_k: int = None) -> Dict:
    start_time = time.time()

    chunks = retrieve_relevant_chunks(lecture_id, question, top_k)

    if not chunks:
        latency_ms = round((time.time() - start_time) * 1000, 1)
        return {
            "answer": NOT_FOUND_MESSAGE,
            "grounded": False,
            "sources": [],
            "latency_ms": latency_ms,
        }

    context = _build_context(chunks)
    user_prompt = (
        f"CONTEXT (transcript excerpts from the lecture):\n{context}\n\n"
        f"QUESTION: {question}\n\n"
        "Answer the question using only the CONTEXT above."
    )

    try:
        answer = generate(RAG_SYSTEM_PROMPT, user_prompt)
    except LLMError as e:
        raise

    grounded = NOT_FOUND_MESSAGE.lower() not in answer.lower()
    latency_ms = round((time.time() - start_time) * 1000, 1)

    return {
        "answer": answer,
        "grounded": grounded,
        "sources": chunks,
        "latency_ms": latency_ms,
    }
