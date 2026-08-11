"""
app/models.py

Implements the Phase 1 design doc's data model exactly. Two things
worth noting up front:

1. Vectors are stored as JSON-encoded float lists in a plain column,
   not pgvector -- the design doc explicitly allows this ("in-DB
   arrays fine at this scale," ~50 images). Cosine similarity is
   computed in Python at query time (Phase 3). This is a real,
   documented tradeoff: pgvector would be the right call past a few
   thousand rows.

2. BatchJob reuses the exact shape from the BE-06/BE-07 assignments
   (idempotency, retries, backoff) -- the capstone brief explicitly
   asks for this pattern to be visible, not reinvented.
"""

import os
import uuid
import enum
import json
from datetime import datetime

from sqlalchemy import (
    create_engine, Column, String, DateTime, Integer, Float, Boolean, Enum, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./image_relevance.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def new_uuid() -> str:
    return str(uuid.uuid4())


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ImageStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    tagged = "tagged"
    failed = "failed"


class Image(Base):
    __tablename__ = "images"

    id = Column(String(36), primary_key=True, default=new_uuid)
    filename = Column(String, nullable=False)
    source_url = Column(String, nullable=True)
    local_path = Column(String, nullable=True)

    subject = Column(String, nullable=True)
    category = Column(String, nullable=True)
    attributes_json = Column(Text, nullable=True)
    caption = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    needs_review = Column(Boolean, nullable=False, default=False)

    status = Column(Enum(ImageStatus), nullable=False, default=ImageStatus.pending, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def attributes(self) -> list[str]:
        return json.loads(self.attributes_json) if self.attributes_json else []

    @attributes.setter
    def attributes(self, value: list[str]):
        self.attributes_json = json.dumps(value)


class ImageEmbedding(Base):
    __tablename__ = "image_embeddings"

    id = Column(String(36), primary_key=True, default=new_uuid)
    image_id = Column(String(36), ForeignKey("images.id"), nullable=False, unique=True, index=True)
    vector_json = Column(Text, nullable=False)
    model_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def vector(self) -> list[float]:
        return json.loads(self.vector_json)


class Post(Base):
    __tablename__ = "posts"

    id = Column(String(36), primary_key=True, default=new_uuid)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PostEmbedding(Base):
    __tablename__ = "post_embeddings"

    id = Column(String(36), primary_key=True, default=new_uuid)
    post_id = Column(String(36), ForeignKey("posts.id"), nullable=False, unique=True, index=True)
    vector_json = Column(Text, nullable=False)
    model_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def vector(self) -> list[float]:
        return json.loads(self.vector_json)


class SuggestionStatus(str, enum.Enum):
    suggested = "suggested"
    approved = "approved"
    rejected = "rejected"


class Suggestion(Base):
    __tablename__ = "suggestions"

    id = Column(String(36), primary_key=True, default=new_uuid)
    post_id = Column(String(36), ForeignKey("posts.id"), nullable=False, index=True)
    image_id = Column(String(36), ForeignKey("images.id"), nullable=False, index=True)
    similarity_score = Column(Float, nullable=False)
    guard_passed = Column(Boolean, nullable=False)
    guard_reason = Column(String, nullable=False)
    status = Column(Enum(SuggestionStatus), nullable=False, default=SuggestionStatus.suggested)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("Post")
    image = relationship("Image")


class CallType(str, enum.Enum):
    vision_tagging = "vision_tagging"
    embedding = "embedding"


class VisionCall(Base):
    __tablename__ = "vision_calls"

    id = Column(String(36), primary_key=True, default=new_uuid)
    image_id = Column(String(36), ForeignKey("images.id"), nullable=True)
    call_type = Column(Enum(CallType), nullable=False)
    tokens_or_units = Column(Integer, nullable=False)
    estimated_cost_usd = Column(Float, nullable=False)
    was_simulated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class BatchJobType(str, enum.Enum):
    tag_images = "tag_images"
    embed_images = "embed_images"
    embed_posts = "embed_posts"


class BatchJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id = Column(String(36), primary_key=True, default=new_uuid)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    job_type = Column(Enum(BatchJobType), nullable=False)
    status = Column(Enum(BatchJobStatus), nullable=False, default=BatchJobStatus.pending, index=True)

    total_items = Column(Integer, nullable=False, default=0)
    processed_items = Column(Integer, nullable=False, default=0)
    failed_items = Column(Integer, nullable=False, default=0)

    error = Column(String, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    next_attempt_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
