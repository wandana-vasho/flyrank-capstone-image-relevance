"""
app/embedding_service.py

Real Gemini embeddings when GEMINI_API_KEY is set. The simulated
fallback is NOT random noise -- it's a deterministic bag-of-words
hash into a fixed-dimension vector, so texts sharing words genuinely
land closer together in cosine similarity than unrelated texts. This
matters: Phase 3's matching and guard logic need real signal to
demonstrate against, even before a real API key exists. Swapping to
the real API changes nothing about how those consume the vectors --
both paths return a plain list[float] of the same dimension.
"""

import os
import re
import hashlib
import logging

log = logging.getLogger("embedding_service")

SIMULATED_DIMENSIONS = 64
REAL_MODEL_NAME = "text-embedding-004"
SIMULATED_MODEL_NAME = "simulated-bow-hash-v1"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _simulate_embedding(text: str) -> list[float]:
    vector = [0.0] * SIMULATED_DIMENSIONS
    tokens = _tokenize(text)
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode()).hexdigest()
        dim = int(digest[:8], 16) % SIMULATED_DIMENSIONS
        sign = 1.0 if int(digest[8], 16) % 2 == 0 else -1.0
        vector[dim] += sign

    magnitude = sum(v * v for v in vector) ** 0.5
    if magnitude == 0:
        return vector
    return [v / magnitude for v in vector]


def _call_real_gemini_embedding(text: str) -> list[float]:
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    result = genai.embed_content(
        model=f"models/{REAL_MODEL_NAME}",
        content=text,
        task_type="SEMANTIC_SIMILARITY",
    )
    return result["embedding"]


def embed_text(text: str) -> tuple[list[float], str, bool]:
    has_key = bool(os.environ.get("GEMINI_API_KEY"))

    if has_key:
        vector = _call_real_gemini_embedding(text)
        return vector, REAL_MODEL_NAME, False

    vector = _simulate_embedding(text)
    return vector, SIMULATED_MODEL_NAME, True


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"Vector dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(y * y for y in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
