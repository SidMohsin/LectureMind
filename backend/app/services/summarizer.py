"""
Hierarchical (chunk-based) lecture summarization service.

Because full lecture transcripts can be very long, the transcript is split
into manageable chunks, an intermediate summary is generated for each
chunk, the intermediate summaries are combined, and a final structured
summary (overview, main concepts, important points, key takeaways) is
generated from the combined intermediate summaries.
"""
import json
import re
from typing import List, Dict
from app.services.llm_provider import generate, LLMError

INTERMEDIATE_CHUNK_WORDS = 700

INTERMEDIATE_SYSTEM_PROMPT = (
    "You summarise a section of a lecture transcript. Write a concise, factual summary "
    "(3-6 sentences) of the key points covered in this section only. Do not add information "
    "that is not present in the text."
)

FINAL_SYSTEM_PROMPT = (
    "You combine partial lecture summaries into one structured final summary. "
    "Respond ONLY with valid JSON (no markdown, no code fences, no extra text) matching exactly "
    "this schema:\n"
    '{"overview": "string", "main_concepts": ["string", ...], '
    '"important_points": ["string", ...], "key_takeaways": ["string", ...]}\n'
    "Base your output only on the provided partial summaries. Do not invent information."
)


def _split_into_word_chunks(text: str, chunk_size_words: int) -> List[str]:
    words = text.split(" ")
    chunks = []
    for i in range(0, len(words), chunk_size_words):
        chunks.append(" ".join(words[i:i + chunk_size_words]))
    return chunks


def _extract_json(raw: str) -> Dict:
    raw = raw.strip()
    # strip markdown code fences if the model added them despite instructions
    raw = re.sub(r"^```(json)?", "", raw.strip())
    raw = re.sub(r"```$", "", raw.strip())
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # attempt to find the first {...} block
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def generate_summary(full_text: str) -> Dict:
    """
    Returns {"overview": str, "main_concepts": [str], "important_points": [str], "key_takeaways": [str]}
    """
    if not full_text.strip():
        raise ValueError("Cannot summarize an empty transcript.")

    text_chunks = _split_into_word_chunks(full_text, INTERMEDIATE_CHUNK_WORDS)

    intermediate_summaries = []
    for chunk in text_chunks:
        try:
            summary = generate(INTERMEDIATE_SYSTEM_PROMPT, f"LECTURE SECTION:\n{chunk}")
        except LLMError:
            raise
        intermediate_summaries.append(summary.strip())

    combined = "\n\n".join(f"Section {i+1} summary: {s}" for i, s in enumerate(intermediate_summaries))

    final_user_prompt = (
        f"Here are partial summaries of consecutive sections of a lecture, in order:\n\n{combined}\n\n"
        "Combine them into one structured final summary following the required JSON schema."
    )

    try:
        raw_final = generate(FINAL_SYSTEM_PROMPT, final_user_prompt)
        parsed = _extract_json(raw_final)
    except (LLMError, json.JSONDecodeError, ValueError):
        # Fallback: build a reasonable structured summary directly from intermediate summaries
        # without inventing content, if the LLM output could not be parsed as JSON.
        parsed = {
            "overview": " ".join(intermediate_summaries[:2]) if intermediate_summaries else "",
            "main_concepts": [],
            "important_points": intermediate_summaries,
            "key_takeaways": [],
        }

    # Normalise expected keys/types
    parsed.setdefault("overview", "")
    parsed.setdefault("main_concepts", [])
    parsed.setdefault("important_points", [])
    parsed.setdefault("key_takeaways", [])
    for key in ("main_concepts", "important_points", "key_takeaways"):
        if not isinstance(parsed[key], list):
            parsed[key] = [str(parsed[key])]

    return parsed
