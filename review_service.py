"""
app/review_service.py

The human-in-the-loop review workflow. Per the brief's explicit scope
guidance ("a simple admin table" / "validated endpoints plus a table
are enough" -- no frontend build required), this is API-only: list
pending suggestions, approve, reject, inspect why a pairing was
suggested or refused. The Suggestion rows themselves are created by
main.py's /posts/:id/images endpoint every time matching+guard runs.
"""

from datetime import datetime
from sqlalchemy.orm import Session

from app.models import Suggestion, SuggestionStatus


class SuggestionNotFoundError(Exception):
    pass


def list_suggestions(db: Session, status: str | None = None) -> list[Suggestion]:
    query = db.query(Suggestion)
    if status:
        query = query.filter(Suggestion.status == status)
    return query.order_by(Suggestion.created_at.desc()).all()


def approve_suggestion(db: Session, suggestion_id: str) -> Suggestion:
    suggestion = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
    if suggestion is None:
        raise SuggestionNotFoundError(f"Suggestion {suggestion_id} not found")
    suggestion.status = SuggestionStatus.approved
    suggestion.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(suggestion)
    return suggestion


def reject_suggestion(db: Session, suggestion_id: str) -> Suggestion:
    suggestion = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
    if suggestion is None:
        raise SuggestionNotFoundError(f"Suggestion {suggestion_id} not found")
    suggestion.status = SuggestionStatus.rejected
    suggestion.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(suggestion)
    return suggestion
