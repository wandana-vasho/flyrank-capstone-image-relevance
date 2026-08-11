"""
main.py -- Phase 2 API surface: kick off batch jobs, poll status, and
check cost. Matching, the guard, and the review API arrive in Phase 3/4.
"""

import os
import logging
import threading

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import (
    Base, engine, get_db, BatchJob, BatchJobType, BatchJobStatus, Image, Post, Suggestion, SuggestionStatus,
)
from app.schemas import BatchJobOut, ImageOut
from app.worker import run_worker_loop
from app.cost_tracking import get_cost_summary
from app.matching_service import rank_images_for_post
from app.guard_service import evaluate_candidate, get_best_guarded_match
from app.review_service import list_suggestions, approve_suggestion, reject_suggestion, SuggestionNotFoundError
from app.eval_service import run_eval

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Image Understanding & Content Matching Engine", version="0.2.0-phase2")

_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


@app.on_event("startup")
def start_worker():
    global _worker_thread
    if os.environ.get("TESTING"):
        return
    _worker_thread = threading.Thread(target=run_worker_loop, args=(_stop_event,), daemon=True)
    _worker_thread.start()


@app.on_event("shutdown")
def stop_worker():
    _stop_event.set()


def _create_batch_job(db: Session, job_type: BatchJobType, idempotency_key: str) -> BatchJob:
    existing = db.query(BatchJob).filter(BatchJob.idempotency_key == idempotency_key).first()
    if existing:
        return existing

    job = BatchJob(idempotency_key=idempotency_key, job_type=job_type)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.query(BatchJob).filter(BatchJob.idempotency_key == idempotency_key).first()
    db.refresh(job)
    return job


@app.post("/batch-jobs/tag-images", response_model=BatchJobOut, status_code=202)
def trigger_tag_images(idempotency_key: str, db: Session = Depends(get_db)):
    job = _create_batch_job(db, BatchJobType.tag_images, idempotency_key)
    return job


@app.post("/batch-jobs/embed-images", response_model=BatchJobOut, status_code=202)
def trigger_embed_images(idempotency_key: str, db: Session = Depends(get_db)):
    job = _create_batch_job(db, BatchJobType.embed_images, idempotency_key)
    return job


@app.post("/batch-jobs/embed-posts", response_model=BatchJobOut, status_code=202)
def trigger_embed_posts(idempotency_key: str, db: Session = Depends(get_db)):
    job = _create_batch_job(db, BatchJobType.embed_posts, idempotency_key)
    return job


@app.get("/batch-jobs/{job_id}", response_model=BatchJobOut)
def get_batch_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(BatchJob).filter(BatchJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Batch job not found")
    return job


@app.get("/images", response_model=list[ImageOut])
def list_images(needs_review: bool | None = None, db: Session = Depends(get_db)):
    query = db.query(Image)
    if needs_review is not None:
        query = query.filter(Image.needs_review == needs_review)
    return query.all()


@app.get("/posts/{post_id}/images")
def get_post_image_suggestions(post_id: str, db: Session = Depends(get_db)):
    """
    Ranks all tagged images against this post by embedding similarity,
    runs EVERY candidate through the guard (not just the winner -- this
    is what lets you literally see the wolf candidate get rejected for
    a fox post, per the brief's PROBE 3), and returns:
      - best_match: the top candidate that actually passed the guard, or null
      - no_confident_match: true if nothing passed, with a reason
      - all_candidates: every ranked candidate with its own pass/fail + reason
    """
    post = db.query(Post).filter(Post.id == post_id).first()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    candidates = rank_images_for_post(db, post_id)

    evaluated = []
    for candidate in candidates:
        result = evaluate_candidate(db, post, candidate)
        evaluated.append({
            "image_id": candidate.image.id,
            "filename": candidate.image.filename,
            "subject": candidate.image.subject,
            "similarity": round(candidate.similarity, 4),
            "guard_passed": result.passed,
            "guard_reason": result.reason,
        })

        # Persist as a Suggestion row so Phase 4's review API has real
        # data to approve/reject against -- upsert on (post_id, image_id).
        existing = (
            db.query(Suggestion)
            .filter(Suggestion.post_id == post_id, Suggestion.image_id == candidate.image.id)
            .first()
        )
        if existing is None:
            db.add(Suggestion(
                post_id=post_id, image_id=candidate.image.id,
                similarity_score=candidate.similarity,
                guard_passed=result.passed, guard_reason=result.reason,
            ))
    db.commit()

    best, best_result = get_best_guarded_match(db, post, candidates)

    return {
        "post_id": post_id,
        "post_title": post.title,
        "best_match": {
            "image_id": best.image.id, "filename": best.image.filename,
            "subject": best.image.subject, "similarity": round(best.similarity, 4),
        } if best else None,
        "no_confident_match": best is None,
        "reason_if_no_match": best_result.reason if best is None else None,
        "all_candidates": evaluated,
    }


@app.get("/suggestions")
def get_suggestions(status: str | None = None, db: Session = Depends(get_db)):
    suggestions = list_suggestions(db, status)
    return [
        {
            "id": s.id, "post_id": s.post_id, "post_title": s.post.title if s.post else None,
            "image_id": s.image_id, "image_filename": s.image.filename if s.image else None,
            "similarity_score": round(s.similarity_score, 4),
            "guard_passed": s.guard_passed, "guard_reason": s.guard_reason,
            "status": s.status.value if hasattr(s.status, "value") else s.status,
            "reviewed_at": s.reviewed_at,
        }
        for s in suggestions
    ]


@app.post("/suggestions/{suggestion_id}/approve")
def approve(suggestion_id: str, db: Session = Depends(get_db)):
    try:
        suggestion = approve_suggestion(db, suggestion_id)
    except SuggestionNotFoundError:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return {"id": suggestion.id, "status": suggestion.status.value}


@app.post("/suggestions/{suggestion_id}/reject")
def reject(suggestion_id: str, db: Session = Depends(get_db)):
    try:
        suggestion = reject_suggestion(db, suggestion_id)
    except SuggestionNotFoundError:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return {"id": suggestion.id, "status": suggestion.status.value}


@app.post("/eval/run")
def eval_run(db: Session = Depends(get_db)):
    return run_eval(db)


@app.get("/costs/summary")
def cost_summary(db: Session = Depends(get_db)):
    return get_cost_summary(db)


@app.get("/health")
def health():
    return {"status": "ok", "worker_alive": _worker_thread.is_alive() if _worker_thread else False}
