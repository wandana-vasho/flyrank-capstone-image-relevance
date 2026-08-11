"""
app/eval_service.py

The brief's closing demo line is a measured number, not a feeling:
"Top-1 precision: X%". This module runs the full matching+guard
pipeline against a small hand-labeled set (post -> the correct
expected image subject, or None if no image should match at all) and
reports the fraction of posts whose top accepted suggestion (or
correct refusal) matches the label.
"""

from sqlalchemy.orm import Session

from app.models import Post
from app.matching_service import rank_images_for_post
from app.guard_service import get_best_guarded_match

EVAL_SET = [
    ("red fox", "red fox"),
    ("wolf pack", "gray wolf"),
    ("dog breeds", "domestic dog"),
    ("bear hibernation", "brown bear"),
    ("deer grazing", "deer"),
    ("roadmap", None),
]


def run_eval(db: Session) -> dict:
    results = []
    correct = 0

    for title_substring, expected_subject in EVAL_SET:
        post = db.query(Post).filter(Post.title.ilike(f"%{title_substring}%")).first()
        if post is None:
            results.append({
                "title_substring": title_substring, "expected": expected_subject,
                "actual": None, "correct": False, "note": "post not found in DB",
            })
            continue

        candidates = rank_images_for_post(db, post.id)
        best, guard_result = get_best_guarded_match(db, post, candidates)
        actual_subject = best.image.subject if best else None

        is_correct = actual_subject == expected_subject
        if is_correct:
            correct += 1

        results.append({
            "post_title": post.title,
            "expected": expected_subject,
            "actual": actual_subject,
            "correct": is_correct,
            "guard_reason": guard_result.reason,
        })

    total = len(results)
    precision = correct / total if total else 0.0

    return {
        "top_1_precision": round(precision, 4),
        "correct": correct,
        "total": total,
        "results": results,
    }
