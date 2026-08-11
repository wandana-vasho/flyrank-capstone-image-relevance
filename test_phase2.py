"""
tests/test_phase2.py

Covers: schema validation (never trust invalid output), the confidence
threshold flagging path, deterministic simulated tagging, embedding
similarity behavior, batch job idempotency + processing correctness,
and cost tracking.
"""

import uuid
from pydantic import ValidationError

from app.vision_schema import VisionTagOutput
from app.vision_service import tag_image, CONFIDENCE_THRESHOLD
from app.embedding_service import embed_text, cosine_similarity
from app.models import SessionLocal, BatchJob, BatchJobType, Image, VisionCall
from app.worker import claim_next_job, process_job
from app.cost_tracking import get_cost_summary


def test_valid_vision_output_parses():
    valid = {
        "subject": "red fox", "category": "animal",
        "attributes": ["orange fur", "wild"],
        "caption": "A fox in a forest.", "confidence": 0.9,
    }
    result = VisionTagOutput.model_validate(valid)
    assert result.subject == "red fox"


def test_missing_field_is_rejected():
    invalid = {"subject": "red fox", "category": "animal"}
    try:
        VisionTagOutput.model_validate(invalid)
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass


def test_confidence_out_of_range_is_rejected():
    invalid = {
        "subject": "red fox", "category": "animal", "attributes": ["wild"],
        "caption": "A fox.", "confidence": 1.5,
    }
    try:
        VisionTagOutput.model_validate(invalid)
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass


def test_empty_attributes_list_is_rejected():
    invalid = {
        "subject": "red fox", "category": "animal", "attributes": [],
        "caption": "A fox.", "confidence": 0.9,
    }
    try:
        VisionTagOutput.model_validate(invalid)
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass


def test_simulated_tagging_matches_filename_category():
    result, was_simulated = tag_image("fox_01.jpg", "fox_01.jpg")
    assert was_simulated is True
    assert "fox" in result.subject.lower()
    assert result.category == "animal"


def test_simulated_tagging_flags_unknown_filenames_as_uncertain():
    result, was_simulated = tag_image("mystery_object.jpg", "mystery_object.jpg")
    assert result.confidence < CONFIDENCE_THRESHOLD


def test_similar_text_produces_higher_similarity_than_unrelated_text():
    fox_a, _, _ = embed_text("red fox wild forest orange")
    fox_b, _, _ = embed_text("red fox species wild orange fur")
    unrelated, _, _ = embed_text("quarterly product roadmap dashboard")

    sim_fox_to_fox = cosine_similarity(fox_a, fox_b)
    sim_fox_to_unrelated = cosine_similarity(fox_a, unrelated)

    assert sim_fox_to_fox > sim_fox_to_unrelated


def test_cosine_similarity_of_identical_vectors_is_one():
    v, _, _ = embed_text("red fox")
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def test_cosine_similarity_rejects_mismatched_dimensions():
    try:
        cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_batch_job_creation_is_idempotent(client):
    key = str(uuid.uuid4())
    first = client.post(f"/batch-jobs/tag-images?idempotency_key={key}")
    second = client.post(f"/batch-jobs/tag-images?idempotency_key={key}")
    assert first.json()["id"] == second.json()["id"]


def test_batch_job_processes_all_pending_images(db_session, sample_images):
    job = BatchJob(idempotency_key=str(uuid.uuid4()), job_type=BatchJobType.tag_images)
    db_session.add(job)
    db_session.commit()

    claimed = claim_next_job(db_session)
    process_job(db_session, claimed)

    db_session.refresh(claimed)
    assert claimed.status.value == "completed"
    assert claimed.total_items == 3
    assert claimed.processed_items == 3

    tagged_images = db_session.query(Image).filter(Image.status == "tagged").all()
    assert len(tagged_images) == 3


def test_low_confidence_images_are_flagged_needs_review(db_session, sample_images):
    job = BatchJob(idempotency_key=str(uuid.uuid4()), job_type=BatchJobType.tag_images)
    db_session.add(job)
    db_session.commit()

    claimed = claim_next_job(db_session)
    process_job(db_session, claimed)

    weird_image = db_session.query(Image).filter(Image.filename == "unknown_weird.jpg").first()
    assert weird_image.needs_review is True


def test_cost_is_logged_per_call(db_session, sample_images):
    job = BatchJob(idempotency_key=str(uuid.uuid4()), job_type=BatchJobType.tag_images)
    db_session.add(job)
    db_session.commit()

    claimed = claim_next_job(db_session)
    process_job(db_session, claimed)

    calls = db_session.query(VisionCall).all()
    assert len(calls) == 3

    summary = get_cost_summary(db_session)
    assert summary["total_calls"] == 3
    assert summary["simulated_calls"] == 3
