"""
Modular LLM provider layer.

Supports three interchangeable providers selected via LLM_PROVIDER env var:
  - "ollama": local LLM via the Ollama REST API (default, no API key needed)
  - "openai": OpenAI-compatible chat completions API
  - "groq":   Groq's OpenAI-compatible chat completions API

All providers expose the same function: generate(system_prompt, user_prompt) -> str
No API key is ever hard-coded; keys are read from environment variables only.
"""
import json
import requests
from app.config import settings


class LLMError(Exception):
    pass


class LLMNotConfiguredError(LLMError):
    pass


def _generate_ollama(system_prompt: str, user_prompt: str) -> str:
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    try:
        resp = requests.post(url, json=payload, timeout=settings.LLM_TIMEOUT_SECONDS)
    except requests.exceptions.ConnectionError as e:
        raise LLMNotConfiguredError(
            f"Could not connect to Ollama at {settings.OLLAMA_BASE_URL}. "
            f"Is Ollama installed and running? Start it with 'ollama serve' and pull the model with "
            f"'ollama pull {settings.OLLAMA_MODEL}'."
        ) from e
    except requests.exceptions.Timeout as e:
        raise LLMError("Ollama request timed out.") from e

    if resp.status_code != 200:
        raise LLMError(f"Ollama returned status {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
        return data["message"]["content"].strip()
    except (KeyError, json.JSONDecodeError) as e:
        raise LLMError(f"Unexpected Ollama response format: {e}") from e


def _generate_openai_compatible(system_prompt: str, user_prompt: str, base_url: str, api_key: str, model: str) -> str:
    if not api_key:
        raise LLMNotConfiguredError(
            "No API key configured for this LLM provider. Set the appropriate key in your .env file."
        )
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=settings.LLM_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout as e:
        raise LLMError("LLM API request timed out.") from e
    except requests.exceptions.RequestException as e:
        raise LLMError(f"LLM API request failed: {e}") from e

    if resp.status_code != 200:
        raise LLMError(f"LLM API returned status {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise LLMError(f"Unexpected LLM API response format: {e}") from e


def generate(system_prompt: str, user_prompt: str) -> str:
    """Route to the configured LLM provider and return the generated text."""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "ollama":
        return _generate_ollama(system_prompt, user_prompt)
    elif provider == "openai":
        return _generate_openai_compatible(
            system_prompt, user_prompt,
            base_url="https://api.openai.com/v1",
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
        )
    elif provider == "groq":
        return _generate_openai_compatible(
            system_prompt, user_prompt,
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_MODEL,
        )
    else:
        raise LLMNotConfiguredError(
            f"Unknown LLM_PROVIDER '{provider}'. Use one of: ollama, openai, groq."
        )
