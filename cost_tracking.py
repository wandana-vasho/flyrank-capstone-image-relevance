"""
app/cost_tracking.py

Logs one row per vision/embedding call. Even on Gemini's free tier
(real billed cost: $0), we track an ESTIMATED cost using Gemini's
public paid-tier rate -- because the habit of attributing cost per
call is the actual requirement (brief: "per-call cost tracking, even
inside a free tier"), not the dollar amount itself.
"""

from sqlalchemy.orm import Session

from app.models import VisionCall, CallType

GEMINI_FLASH_VISION_COST_PER_CALL = 0.0004
GEMINI_EMBEDDING_COST_PER_1K_CHARS = 0.00001


def log_vision_call(db: Session, image_id: str, was_simulated: bool) -> VisionCall:
    call = VisionCall(
        image_id=image_id,
        call_type=CallType.vision_tagging,
        tokens_or_units=1,
        estimated_cost_usd=0.0 if was_simulated else GEMINI_FLASH_VISION_COST_PER_CALL,
        was_simulated=was_simulated,
    )
    db.add(call)
    db.commit()
    return call


def log_embedding_call(db: Session, image_id: str | None, text_length: int, was_simulated: bool) -> VisionCall:
    estimated = 0.0 if was_simulated else (text_length / 1000) * GEMINI_EMBEDDING_COST_PER_1K_CHARS
    call = VisionCall(
        image_id=image_id,
        call_type=CallType.embedding,
        tokens_or_units=text_length,
        estimated_cost_usd=round(estimated, 8),
        was_simulated=was_simulated,
    )
    db.add(call)
    db.commit()
    return call


def get_cost_summary(db: Session) -> dict:
    calls = db.query(VisionCall).all()
    total_cost = sum(c.estimated_cost_usd for c in calls)
    by_type: dict[str, dict] = {}
    for c in calls:
        key = c.call_type.value if hasattr(c.call_type, "value") else c.call_type
        by_type.setdefault(key, {"count": 0, "cost": 0.0})
        by_type[key]["count"] += 1
        by_type[key]["cost"] += c.estimated_cost_usd

    return {
        "total_calls": len(calls),
        "total_estimated_cost_usd": round(total_cost, 6),
        "by_call_type": {k: {"count": v["count"], "cost_usd": round(v["cost"], 6)} for k, v in by_type.items()},
        "simulated_calls": sum(1 for c in calls if c.was_simulated),
        "real_calls": sum(1 for c in calls if not c.was_simulated),
    }
