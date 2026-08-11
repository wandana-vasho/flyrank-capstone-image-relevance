"""
app/vision_service.py

Calls Gemini Flash for real image tagging when GEMINI_API_KEY is set.
Without a key, falls back to a deterministic simulator -- same pattern
used in the BE-06/BE-07 assignments: the whole system is buildable and
testable at $0, and swapping in the real API touches nothing outside
this one function.

Every response -- real or simulated -- passes through the SAME schema
validation path. The simulator is not a shortcut around validation;
it's a stand-in for the untrusted network call, nothing else.
"""

import os
import re
import json
import random
import logging

from pydantic import ValidationError

from app.vision_schema import VisionTagOutput

log = logging.getLogger("vision_service")

CONFIDENCE_THRESHOLD = 0.75  # tuned against the eval set in Phase 4 -- not final

VISION_PROMPT = """Look at this image and respond with ONLY a JSON object matching this exact shape, no other text:
{"subject": "<main subject, 1-4 words>", "category": "<broad category, 1-2 words>", "attributes": ["<3-5 short descriptive attributes>"], "caption": "<one sentence describing the image>", "confidence": <float 0-1, your own certainty>}"""


class VisionCallError(Exception):
    pass


_SIMULATED_SUBJECTS = {
    "fox": {
        "subject": "red fox", "category": "animal",
        "attributes": ["orange fur", "wild", "forest", "bushy tail"],
        "caption": "A red fox standing in a forest.",
    },
    "wolf": {
        "subject": "gray wolf", "category": "animal",
        "attributes": ["gray fur", "wild", "forest", "pack animal"],
        "caption": "A gray wolf in a forest setting.",
    },
    "dog": {
        "subject": "domestic dog", "category": "animal",
        "attributes": ["domesticated", "friendly", "pet", "collar"],
        "caption": "A domestic dog outdoors.",
    },
    "bear": {
        "subject": "brown bear", "category": "animal",
        "attributes": ["large", "brown fur", "wild", "powerful"],
        "caption": "A brown bear in its natural habitat.",
    },
    "deer": {
        "subject": "deer", "category": "animal",
        "attributes": ["antlers", "wild", "forest", "grazing"],
        "caption": "A deer standing in a woodland clearing.",
    },
}


def _simulate_vision_call(filename: str) -> dict:
    lower = filename.lower()
    match = next((key for key in _SIMULATED_SUBJECTS if key in lower), None)

    if match is None:
        return {
            "subject": "unidentified object", "category": "unknown",
            "attributes": ["unclear", "low detail"],
            "caption": "The subject of this image could not be confidently identified.",
            "confidence": round(random.uniform(0.3, 0.6), 2),
        }

    base = dict(_SIMULATED_SUBJECTS[match])
    base["confidence"] = round(random.uniform(0.55, 0.98), 2)
    return base


def _call_real_gemini(image_path: str) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-flash-latest")

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    response = model.generate_content([
        VISION_PROMPT,
        {"mime_type": "image/jpeg", "data": image_bytes},
    ])

    raw_text = response.text.strip()
    raw_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip())
    return json.loads(raw_text)


def tag_image(image_path: str, filename: str) -> tuple[VisionTagOutput, bool]:
    has_key = bool(os.environ.get("GEMINI_API_KEY"))

    try:
        if has_key:
            raw = _call_real_gemini(image_path)
            was_simulated = False
        else:
            raw = _simulate_vision_call(filename)
            was_simulated = True
    except Exception as e:
        raise VisionCallError(f"Vision API call failed: {e}") from e

    try:
        validated = VisionTagOutput.model_validate(raw)
    except ValidationError as e:
        raise VisionCallError(f"Vision response failed schema validation: {e}") from e

    return validated, was_simulated
