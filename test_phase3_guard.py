"""
tests/test_phase3_guard.py

Covers matching + the mismatch guard. Includes a regression test for
a real false positive caught during manual end-to-end testing: an
unrelated post scored a spuriously high similarity against an
unrelated image purely from embedding hash-collision noise, and the
guard incorrectly accepted it. This test exists specifically so that
bug can never silently come back.
"""

import json

from app.models import Image, Post, ImageEmbedding, PostEmbedding
from app.embedding_service import embed_text
from app.matching_service import rank_images_for_post, RankedCandidate
from app.guard_service import evaluate_candidate, get_best_guarded_match


def _make_tagged_image(db, filename, subject, category, confidence=0.9):
    image = Image(
        filename=filename, local_path=filename,
        subject=subject, category=category, confidence=confidence,
        needs_review=confidence < 0.75, status="tagged",
    )
    image.attributes = ["test"]
    image.caption = f"A {subject}."
    db.add(image)
    db.commit()

    vector, model_name, _ = embed_text(f"{subject}. {image.caption}")
    embedding = ImageEmbedding(image_id=image.id, model_name=model_name)
    embedding.vector_json = json.dumps(vector)
    db.add(embedding)
    db.commit()
    return image


def _make_embedded_post(db, title, body):
    post = Post(title=title, body=body)
    db.add(post)
    db.commit()

    vector, model_name, _ = embed_text(f"{title}. {body}")
    embedding = PostEmbedding(post_id=post.id, model_name=model_name)
    embedding.vector_json = json.dumps(vector)
    db.add(embedding)
    db.commit()
    return post


def test_fox_post_ranks_fox_image_highest(db_session):
    fox = _make_tagged_image(db_session, "fox_a.jpg", "red fox", "animal")
    wolf = _make_tagged_image(db_session, "wolf_a.jpg", "gray wolf", "animal")
    post = _make_embedded_post(
        db_session, "The behavior of red foxes",
        "Red foxes are wild canids with distinctive orange fur found in forests.",
    )

    ranked = rank_images_for_post(db_session, post.id)
    assert ranked[0].image.id == fox.id


def test_wolf_is_rejected_for_fox_post_with_category_mismatch_reason(db_session):
    fox = _make_tagged_image(db_session, "fox_b.jpg", "red fox", "animal")
    wolf = _make_tagged_image(db_session, "wolf_b.jpg", "gray wolf", "animal")
    post = _make_embedded_post(
        db_session, "The behavior of red foxes",
        "Red foxes are wild canids with distinctive orange fur found in forests.",
    )

    wolf_candidate = RankedCandidate(wolf, similarity=0.9)
    result = evaluate_candidate(db_session, post, wolf_candidate)

    assert result.passed is False
    assert "mismatch" in result.reason.lower() or "expected" in result.reason.lower()


def test_low_confidence_image_is_rejected_even_with_good_similarity(db_session):
    fox = _make_tagged_image(db_session, "fox_c.jpg", "red fox", "animal", confidence=0.5)
    post = _make_embedded_post(db_session, "Red fox facts", "Red foxes have orange fur.")

    candidate = RankedCandidate(fox, similarity=0.9)
    result = evaluate_candidate(db_session, post, candidate)

    assert result.passed is False
    assert "confidence" in result.reason.lower()


def test_unrelated_post_gets_no_confident_match_not_a_false_positive(db_session):
    deer = _make_tagged_image(db_session, "deer_a.jpg", "deer", "animal")
    post = _make_embedded_post(
        db_session, "Quarterly product roadmap update",
        "This quarter we shipped a redesigned API dashboard and improved rate limiting.",
    )

    forced_candidate = RankedCandidate(deer, similarity=0.99)
    result = evaluate_candidate(db_session, post, forced_candidate)

    assert result.passed is False
    assert "known image subject" in result.reason.lower()


def test_no_tagged_images_returns_no_confident_match_cleanly(db_session):
    post = _make_embedded_post(db_session, "Red fox facts", "Foxes are wild.")
    best, result = get_best_guarded_match(db_session, post, [])
    assert best is None
    assert result.passed is False


def test_get_best_guarded_match_skips_failing_candidates_and_returns_the_first_pass(db_session):
    fox_low_conf = _make_tagged_image(db_session, "fox_d.jpg", "red fox", "animal", confidence=0.5)
    fox_good = _make_tagged_image(db_session, "fox_e.jpg", "red fox", "animal", confidence=0.9)
    post = _make_embedded_post(db_session, "Red fox facts", "Foxes have orange fur and live in forests.")

    candidates = [
        RankedCandidate(fox_low_conf, similarity=0.9),
        RankedCandidate(fox_good, similarity=0.2),
    ]
    best, result = get_best_guarded_match(db_session, post, candidates)

    assert best is not None
    assert best.image.id == fox_good.id
    assert result.passed is True
