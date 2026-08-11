import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["TESTING"] = "1"
os.environ["DATABASE_URL"] = "sqlite:///./test_image_relevance.db"
os.environ.pop("GEMINI_API_KEY", None)

import pytest
from fastapi.testclient import TestClient

from app.models import Base, engine, SessionLocal, Image, Post
import main


@pytest.fixture(scope="function", autouse=True)
def clean_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    main._worker_thread = None
    return TestClient(main.app)


@pytest.fixture
def db_session():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sample_images(db_session):
    images = [
        Image(filename="fox_01.jpg", local_path="fox_01.jpg"),
        Image(filename="wolf_01.jpg", local_path="wolf_01.jpg"),
        Image(filename="unknown_weird.jpg", local_path="unknown_weird.jpg"),
    ]
    db_session.add_all(images)
    db_session.commit()
    return images


@pytest.fixture
def sample_posts(db_session):
    posts = [
        Post(title="Red fox behavior", body="Red foxes are wild canids with orange fur."),
        Post(title="Wolf packs", body="Gray wolves hunt in coordinated packs."),
    ]
    db_session.add_all(posts)
    db_session.commit()
    return posts
