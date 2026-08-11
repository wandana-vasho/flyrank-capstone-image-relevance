"""
app/vision_schema.py

The schema every raw vision-model response is validated against before
anything trusts it. This is the literal implementation of the brief's
"never trust invalid model output" rule -- if a response doesn't parse
against this, it's a validation failure, handled by the caller
(vision_service.py), never silently accepted.
"""

from pydantic import BaseModel, Field, field_validator


class VisionTagOutput(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=50)
    attributes: list[str] = Field(min_length=1, max_length=10)
    caption: str = Field(min_length=1, max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("attributes")
    @classmethod
    def attributes_not_empty_strings(cls, v: list[str]) -> list[str]:
        cleaned = [a.strip() for a in v if a.strip()]
        if not cleaned:
            raise ValueError("attributes list contained only empty strings")
        return cleaned
