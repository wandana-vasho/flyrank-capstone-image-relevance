"""
tests/test_phase4_review_eval.py
"""

import json
from app.models import Post, Image, ImageEmbedding, PostEmbedding, Suggestion, SuggestionStatus
from app.embedding_service import embed_text
from app.review_service import list_suggestions, approve_suggestion, reject_suggestion, SuggestionNotFoundError
from app.eval_service import run_eval


def _make_suggestion(db, guard_passed=True):
    post = Post(title="Test post", body="Test body")
    image = Image(filename="test.jpg", local_path="test.jpg", subject="test subject", status="tagged")
    db.add_all([post, image])
    db.commit()

    suggestion = Suggestion(
        post_id=post.id, image_id=image.id, similarity_score=0.5,
        guard_passed=guard_passed, guard_reason="test reason",
    )
    db.add(suggestion)
    db.commit()
    return suggestion


def test_approve_suggestion_updates_status_and_timestamp(db_session):
    suggestion = _make_suggestion(db_session)
    updated = approve_suggestion(db_session, suggestion.id)
    assert updated.status == SuggestionStatus.approved
    assert updated.reviewed_at is not None


def test_reject_suggestion_updates_status(db_session):
    suggestion = _make_suggestion(db_session)
    updated = reject_suggestion(db_session, suggestion.id)
    assert updated.status == SuggestionStatus.rejected


def test_approving_nonexistent_suggestion_raises():
    from app.models import SessionLocal
    db = SessionLocal()
    try:
        approve_suggestion(db, "nonexistent-id")
        assert False, "Should have raised SuggestionNotFoundError"
    except SuggestionNotFoundError:
        pass
    finally:
        db.close()


def test_list_suggestions_filters_by_status(db_session):
    s1 = _make_suggestion(db_session)
    s2 = _make_suggestion(db_session)
    approve_suggestion(db_session, s1.id)

    approved = list_suggestions(db_session, "approved")
    assert len(approved) == 1
    assert approved[0].id == s1.id


def test_review_api_endpoints(client, db_session):
    suggestion = _make_suggestion(db_session)

    list_resp = client.get("/suggestions")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    approve_resp = client.post(f"/suggestions/{suggestion.id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"


def test_eval_run_returns_precision_and_per_case_results(db_session):
    fox = Image(filename="fox.jpg", local_path="fox.jpg", subject="red fox", category="animal",
                confidence=0.9, status="tagged")
    fox.attributes = ["orange"]
    fox.caption = "A red fox."
    db_session.add(fox)
    db_session.commit()

    vector, model_name, _ = embed_text("red fox. A red fox.")
    fox_emb = ImageEmbedding(image_id=fox.id, model_name=model_name)
    fox_emb.vector_json = json.dumps(vector)
    db_session.add(fox_emb)

    post = Post(title="red fox facts", body="Red foxes have orange fur and live in forests.")
    db_session.add(post)
    db_session.commit()

    post_vector, post_model, _ = embed_text(f"{post.title}. {post.body}")
    post_emb = PostEmbedding(post_id=post.id, model_name=post_model)
    post_emb.vector_json = json.dumps(post_vector)
    db_session.add(post_emb)
    db_session.commit()

    result = run_eval(db_session)
    assert "top_1_precision" in result
    assert result["total"] == len(result["results"])
    assert result["correct"] <= result["total"]
    assert result["top_1_precision"] == round(result["correct"] / result["total"], 4)
