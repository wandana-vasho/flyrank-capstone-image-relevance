# Design Doc — AI Image Understanding & Content Matching Engine

**Wandana Vasho · FlyRank Backend AI Engineering Capstone #2**

## Problem

Given a library of ~50 images and a set of blog posts, automatically
tag every image with structured, schema-validated metadata (subject,
category, attributes, caption, confidence), embed both images and
posts into a shared semantic space, and for each post rank the best
matching image — but refuse to suggest anything when no image clears
a confidence bar, explaining why. The core deliverable isn't finding
matches; it's correctly *not* matching a wolf photo to a fox post.

## Image metadata schema

Every vision-model response is validated against this shape before
anything downstream trusts it:

```json
{
  "subject": "red fox",
  "category": "animal",
  "attributes": ["orange fur", "wild", "forest"],
  "caption": "A red fox standing in a forest",
  "confidence": 0.94
}
```

`confidence < CONFIDENCE_THRESHOLD` (tuned in Phase 4 against the eval
set, not guessed) → the image is flagged for review rather than
silently accepted into the matching pool.

## Data model

```
Image
  id (uuid, pk)
  filename
  source_url          -- Unsplash/Pexels attribution
  subject              -- from vision output, nullable until processed
  category
  attributes (jsonb)
  caption
  confidence (float)
  needs_review (bool)  -- true if confidence < threshold
  status (enum: pending | processing | tagged | failed)
  created_at, updated_at

ImageEmbedding
  id (uuid, pk)
  image_id (fk -> Image, unique, indexed)
  vector (float[])      -- embedding of the caption
  model_name             -- which embedding model produced this

Post
  id (uuid, pk)
  title
  body
  created_at

PostEmbedding
  id (uuid, pk)
  post_id (fk -> Post, unique, indexed)
  vector (float[])
  model_name

Suggestion
  id (uuid, pk)
  post_id (fk -> Post, indexed)
  image_id (fk -> Image, indexed)
  similarity_score (float)
  guard_passed (bool)
  guard_reason (text)        -- populated whether passed or rejected
  status (enum: suggested | approved | rejected)
  reviewed_at (nullable)
  created_at

VisionCall  -- cost tracking, one row per API call
  id (uuid, pk)
  image_id (fk -> Image, nullable -- also used for embedding calls)
  call_type (enum: vision_tagging | embedding)
  tokens_or_units (int)
  estimated_cost_usd (float)
  created_at

BatchJob   -- reuses the BE-06/BE-07 job pattern
  id (uuid, pk)
  job_type (enum: tag_images | embed_images | embed_posts)
  status (enum: pending | running | completed | failed)
  attempts, max_attempts, next_attempt_at
  total_items, processed_items, failed_items
  created_at, updated_at
```

Indexes: `Image.status`, `Suggestion.post_id`, `Suggestion.image_id`,
`ImageEmbedding.image_id` (unique), `PostEmbedding.post_id` (unique).

## API surface

**Ingestion (authenticated or open — single-tenant scope for this capstone)**
- `POST /images` — register an image (upload or URL) for processing
- `POST /batch-jobs/tag-images` — kick off the vision-tagging batch job
- `POST /batch-jobs/embed-all` — kick off embedding generation for images + posts
- `GET /batch-jobs/{id}` — status, progress (processed/total), cost so far

**Matching**
- `GET /posts/{id}/images` — ranked suggestions for a post, guard-filtered
- `GET /images/{id}` — single image's metadata + processing status

**Review**
- `GET /suggestions?status=suggested` — pending review queue
- `POST /suggestions/{id}/approve`
- `POST /suggestions/{id}/reject`

**Eval & cost**
- `POST /eval/run` — runs the labeled eval set, returns top-1 precision
- `GET /costs/summary` — total cost, cost per call type

## Layer sketch

```
HTTP layer (FastAPI routers)
        |
Service layer
  - vision_service: calls Gemini, validates schema, flags low-confidence
  - embedding_service: calls Gemini embeddings, stores vectors
  - matching_service: cosine similarity ranking
  - guard_service: the mismatch guard — tags + threshold + confidence
  - review_service: approve/reject workflow
  - eval_service: runs labeled set, computes top-1 precision
        |
Repository layer
  - all DB access, all tenant/ownership filtering (single-tenant here,
    but the boundary stays real so it's not a rewrite later)
        |
Database (Postgres via Docker)
```

Why this split: the rubric explicitly rewards "swap the DB or a
provider without touching business logic." `vision_service` and
`embedding_service` are the only two places that know Gemini exists —
swapping to Ollama later means touching two files, not the whole
system.

## Non-goal (explicit)

**Not building:** a frontend UI for the review workflow. Per the
brief's own scope guidance ("a simple admin table" is enough, "no
frontend build" required), the review workflow will be validated API
endpoints plus a returned table/list — not a built React admin panel.
Time saved here goes toward the two genuinely hard parts: tuning the
guard's thresholds against real eval data, and getting batch
processing + cost tracking actually correct — both explicitly weighted
×3 and ×2 in the rubric, versus zero rubric weight for a polished UI.

## Stack

- **Backend:** Python + FastAPI
- **Vision + embeddings:** Gemini Flash free tier (Google AI Studio key)
- **Schema validation:** Pydantic
- **Database:** PostgreSQL via Docker
- **Image corpus:** Unsplash (licensed-free), ~50 images across 4-5
  animal categories (red fox, wolf, dog, bear, deer) — chosen
  specifically because fox/wolf is a genuinely hard near-miss pair,
  which is what makes the guard's rejection demo land.
