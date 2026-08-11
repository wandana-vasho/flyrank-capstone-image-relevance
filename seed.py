"""
seed.py -- builds the image corpus (real or placeholder) and seeds
Image rows pointing at it, plus a handful of blog posts to match
against in Phase 3.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.models import SessionLocal, Base, engine, Image, Post

Base.metadata.create_all(bind=engine)

CORPUS_DIR = Path(__file__).parent / "corpus" / "images"

POSTS = [
    {
        "title": "The behavior of red foxes",
        "body": (
            "Red foxes (Vulpes vulpes) are highly adaptable animals found across "
            "forests, grasslands, and increasingly urban areas. Known for their "
            "distinctive orange-red fur and bushy tail, they are solitary hunters "
            "that rely on sharp hearing to locate prey beneath snow or leaf litter."
        ),
    },
    {
        "title": "Understanding wolf pack dynamics",
        "body": (
            "Gray wolves live and hunt in coordinated packs, typically led by a "
            "breeding pair. Their gray fur and larger build distinguish them from "
            "solitary canids. Pack structure, territory marking, and cooperative "
            "hunting are central to wolf survival strategies."
        ),
    },
    {
        "title": "A guide to popular dog breeds",
        "body": (
            "Domestic dogs have been bred alongside humans for thousands of years, "
            "resulting in enormous variety in size, temperament, and appearance. "
            "From working breeds to companion animals, dogs remain one of the most "
            "diverse domesticated species on the planet."
        ),
    },
    {
        "title": "Brown bear hibernation patterns",
        "body": (
            "Brown bears enter a state of hibernation during winter months, "
            "surviving on fat reserves built up during the preceding months. Their "
            "large size and powerful build make them apex predators across much of "
            "their range in North America, Europe, and Asia."
        ),
    },
    {
        "title": "Deer grazing habits across seasons",
        "body": (
            "Deer are herbivorous mammals recognized by their antlers and graceful "
            "movement through woodland clearings. Their grazing patterns shift "
            "seasonally, following the availability of grasses, shoots, and browse "
            "throughout the year."
        ),
    },
    {
        "title": "Quarterly product roadmap update",
        "body": (
            "This quarter we shipped three major features focused on developer "
            "experience: a redesigned API dashboard, improved rate limiting, and "
            "a new webhook retry system. No image in an animal-photo corpus should "
            "be a good match for this post -- it's here specifically to exercise "
            "the 'no confident match' path."
        ),
    },
]


def seed():
    db = SessionLocal()

    if db.query(Post).count() == 0:
        for p in POSTS:
            db.add(Post(title=p["title"], body=p["body"]))
        db.commit()
        print(f"Seeded {len(POSTS)} posts.")
    else:
        print("Posts already seeded -- skipping.")

    image_files = sorted(CORPUS_DIR.glob("*.jpg"))
    if not image_files:
        print(f"No images found in {CORPUS_DIR} -- run corpus/download_corpus.py first.")
    elif db.query(Image).count() == 0:
        for f in image_files:
            db.add(Image(filename=f.name, local_path=str(f)))
        db.commit()
        print(f"Seeded {len(image_files)} image rows.")
    else:
        print("Images already seeded -- skipping.")

    db.close()


if __name__ == "__main__":
    seed()
