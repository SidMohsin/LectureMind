"""
Keyword extraction service.

Primary strategy: ask the LLM to extract 10-20 important lecture terms as
structured JSON. Fallback strategy (used if the LLM call/parse fails):
TF-IDF based keyword extraction using scikit-learn, so the feature keeps
working even without a configured LLM.
"""
import json
import re
from typing import List
from app.services.llm_provider import generate, LLMError

KEYWORD_SYSTEM_PROMPT = (
    "Extract the most important technical terms and concepts from the given lecture transcript. "
    "Respond ONLY with valid JSON (no markdown, no extra text) matching exactly this schema: "
    '{"keywords": ["string", ...]}. Provide between 10 and 20 keywords, ordered by importance, '
    "using terms that actually appear in or are directly discussed in the transcript. Do not invent terms."
)


def _extract_json_keywords(raw: str) -> List[str]:
    raw = raw.strip()
    raw = re.sub(r"^```(json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))
    keywords = data.get("keywords", [])
    return [str(k).strip() for k in keywords if str(k).strip()]


def _tfidf_fallback(full_text: str, top_n: int = 15) -> List[str]:
    from sklearn.feature_extraction.text import TfidfVectorizer

    # Split into pseudo-documents (sentences) so TF-IDF has something to compare against.
    sentences = re.split(r"(?<=[.!?])\s+", full_text)
    sentences = [s for s in sentences if len(s.split()) > 3]
    if len(sentences) < 2:
        sentences = [full_text, full_text]

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        max_features=200,
    )
    tfidf_matrix = vectorizer.fit_transform(sentences)
    scores = tfidf_matrix.sum(axis=0).A1
    terms = vectorizer.get_feature_names_out()
    ranked = sorted(zip(terms, scores), key=lambda x: x[1], reverse=True)
    keywords = [t.title() for t, _ in ranked[:top_n]]
    return keywords


def extract_keywords(full_text: str) -> List[str]:
    if not full_text.strip():
        raise ValueError("Cannot extract keywords from an empty transcript.")

    try:
        raw = generate(KEYWORD_SYSTEM_PROMPT, f"LECTURE TRANSCRIPT:\n{full_text[:8000]}")
        keywords = _extract_json_keywords(raw)
        if keywords:
            return keywords[:20]
    except (LLMError, json.JSONDecodeError, ValueError):
        pass

    # Fallback: TF-IDF based extraction, always available offline.
    return _tfidf_fallback(full_text)
