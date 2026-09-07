from __future__ import annotations

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from common.config import get_settings

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def embed_query(text: str) -> list[float]:
    settings = get_settings()
    response = get_client().models.embed_content(model=settings.gemini_embedding_model, contents=text)
    return response.embeddings[0].values


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def generate_json(prompt: str) -> str:
    settings = get_settings()
    response = get_client().models.generate_content(
        model=settings.gemini_criteria_model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return response.text
