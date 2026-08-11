"""
app/matching_service.py

For a given post, ranks all tagged images by cosine similarity between
the post's embedding and each image's embedding. This module knows
NOTHING about what makes a match "good enough" -- that judgment call
lives entirely in guard_service.py. Keeping ranking and gating
separate means the guard's thresholds can be tuned (Phase 4, against
real eval data) without touching a single line of ranking logic.
"""

from sqlalchemy.orm import Session

from app.models import Image, ImageEmbedding, Post, PostEmbedding
from app.embedding_service import cosine_similarity


class RankedCandidate:
    def __init__(self, image: Image, similarity: float):
        self.image = image
        self.similarity = similarity


def rank_images_for_post(db: Session, post_id: str) -> list[RankedCandidate]:
    post_embedding = db.query(PostEmbedding).filter(PostEmbedding.post_id == post_id).first()
    if post_embedding is None:
        return []

    post_vector = post_embedding.vector

    image_embeddings = db.query(ImageEmbedding).all()
    candidates = []
    for ie in image_embeddings:
        image = db.query(Image).filter(Image.id == ie.image_id).first()
        if image is None or image.status != "tagged":
            continue
        similarity = cosine_similarity(post_vector, ie.vector)
        candidates.append(RankedCandidate(image, similarity))

    candidates.sort(key=lambda c: c.similarity, reverse=True)
    return candidates
