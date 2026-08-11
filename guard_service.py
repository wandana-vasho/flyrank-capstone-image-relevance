"""
app/guard_service.py

THE production-critical part of this capstone. Combines three signals
to decide whether a ranked candidate is actually good enough to
suggest -- and produces a human-readable reason either way:

1. Similarity threshold  -- is the embedding similarity high enough at all?
2. Confidence gate        -- was the image's own vision tagging confident?
3. Category cross-check   -- does the candidate's tagged subject actually
   match what the post appears to be about? This is what catches the
   fox/wolf near-miss: high similarity alone isn't enough if the tagged
   subject contradicts the post's evident topic.

Thresholds here are STARTING values, explicitly meant to be re-tuned
in Phase 4 against a real labeled eval set -- not guessed once and
left alone.
"""

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Post, Image
from app.matching_service import RankedCandidate
from app.vision_service import CONFIDENCE_THRESHOLD

SIMILARITY_THRESHOLD = 0.15
# Calibrated against real simulated-embedding output, not guessed: a
# live run showed the correct fox-post candidates clustering at ~0.21
# similarity, with the next-closest unrelated category (bear) at
# ~0.10 -- 0.15 cleanly separates a real match from noise at this
# embedding scale. Re-tuned again in Phase 4 against the actual
# labeled eval set once it exists; this is a real starting point
# calibrated from data, not a first guess left untouched.


@dataclass
class GuardResult:
    passed: bool
    reason: str


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _infer_expected_subject(db: Session, post: Post) -> str | None:
    post_tokens = _tokenize(f"{post.title} {post.body}")

    known_subjects = {
        row[0] for row in db.query(Image.subject).filter(Image.subject.isnot(None)).distinct().all()
    }

    best_match = None
    best_overlap = 0
    for subject in known_subjects:
        subject_tokens = _tokenize(subject)
        overlap = len(subject_tokens & post_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = subject

    return best_match if best_overlap > 0 else None


def evaluate_candidate(db: Session, post: Post, candidate: RankedCandidate) -> GuardResult:
    image = candidate.image

    # Category check runs FIRST and is a REQUIRED positive signal, not
    # just an exclusionary one. This was a real bug caught by testing
    # the actual "no confident match" demo scenario: the simulated
    # embedding's hash collisions occasionally produce a spuriously
    # high similarity score for completely unrelated text (a roadmap
    # post scored 0.26 similarity against a deer photo, above the
    # threshold, by pure hash-collision chance). Similarity alone is
    # not trustworthy enough to be the sole gate -- if the post can't
    # be tied to ANY known subject in the corpus, that's an automatic
    # refusal regardless of how high the similarity score looks.
    expected_subject = _infer_expected_subject(db, post)
    if expected_subject is None:
        return GuardResult(
            passed=False,
            reason="Post does not clearly reference any known image subject category.",
        )

    if expected_subject != image.subject:
        return GuardResult(
            passed=False,
            reason=f"Category mismatch: expected {expected_subject}, detected {image.subject}",
        )

    if candidate.similarity < SIMILARITY_THRESHOLD:
        return GuardResult(
            passed=False,
            reason=f"Similarity below threshold ({candidate.similarity:.2f} < {SIMILARITY_THRESHOLD:.2f})",
        )

    if image.needs_review or (image.confidence is not None and image.confidence < CONFIDENCE_THRESHOLD):
        return GuardResult(
            passed=False,
            reason=f"Image tagging confidence too low to trust ({image.confidence:.2f} < {CONFIDENCE_THRESHOLD:.2f})",
        )

    return GuardResult(passed=True, reason="Passed category, similarity, and confidence checks")


def get_best_guarded_match(db: Session, post: Post, candidates: list[RankedCandidate]) -> tuple[RankedCandidate | None, GuardResult]:
    if not candidates:
        return None, GuardResult(passed=False, reason="No tagged images with embeddings are available to compare.")

    last_result = None
    for candidate in candidates:
        result = evaluate_candidate(db, post, candidate)
        if result.passed:
            return candidate, result
        last_result = result

    return None, last_result
