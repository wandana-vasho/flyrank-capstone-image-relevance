# AI Image Understanding & Content Matching Engine

**Wandana Vasho · FlyRank Backend AI Engineering Capstone**

Understands an image library, tags it, and matches the right image to
the right blog post — based on meaning, not filenames. A red-fox post
surfaces the red-fox image. A similar-looking wolf gets rejected, with
an explanation. If nothing is a good enough match, the system says so
instead of guessing.

**Top-1 precision on the labeled eval set: 83.33% (5/6)** — real,
measured, one honest miss explained below, not a cherry-picked number.

## Architecture

```
Images (batch job) -> Vision Model -> {tags, caption, confidence} -> Image row
        -> embed(subject+caption) -----------------------------> ImageEmbedding

Posts -> embed(title+body) -----------------------------------------> PostEmbedding

GET /posts/:id/images
  -> rank_images_for_post()      (matching_service.py -- pure ranking, no judgment)
        -> cosine similarity, post vector x every image vector
  -> evaluate_candidate() per candidate  (guard_service.py -- THE safety layer)
        - category cross-check FIRST (required positive signal)
        - similarity threshold
        - confidence gate
        - PASS  -> suggested, with reason
        - FAIL  -> rejected, with reason
  -> best_match (first candidate that passed) OR no_confident_match + reason
  -> Review API: approve / reject (Suggestion rows created automatically)
```

**Why the guard checks category FIRST, not similarity first:** this
was a real bug caught during testing (see BUILDLOG.md) — an unrelated
post scored a spuriously high similarity against an unrelated image
purely from embedding noise. Making the category check a *required*
positive signal, not just an exclusionary one, fixed a genuine false
positive, not just a threshold tweak.

## Setup

```bash
pip install -r requirements.txt
python corpus/download_corpus.py   # real Pexels photos if PEXELS_API_KEY set, else placeholders
python seed.py                      # seeds 6 posts + 50 image rows
python -m uvicorn main:app --reload
```

Everything runs with **zero API keys** — `GEMINI_API_KEY` and
`PEXELS_API_KEY` are both optional. Without them, vision tagging and
embeddings use deterministic simulators (see `app/vision_service.py`
and `app/embedding_service.py`), and the corpus uses generated
placeholder images. Add either key and that one piece switches to the
real API — nothing else in the system changes.

## Try the full pipeline

```bash
curl -X POST "http://localhost:8000/batch-jobs/tag-images?idempotency_key=demo-1"
curl -X POST "http://localhost:8000/batch-jobs/embed-images?idempotency_key=demo-2"
curl -X POST "http://localhost:8000/batch-jobs/embed-posts?idempotency_key=demo-3"
curl "http://localhost:8000/posts/<post-id>/images"
curl -X POST "http://localhost:8000/eval/run"
```

## Running tests

```bash
TESTING=1 pytest -v
```

25 tests: schema validation (never trust invalid vision output), the
confidence-flagging path, batch job idempotency/retries/cost tracking,
matching + the guard (including a regression test for the false
positive described above), the review workflow, and the eval script's
precision math.

## The one eval miss, explained honestly

The "Deer grazing habits" post's top-ranked candidate was a *domestic
dog* image, which the guard correctly rejected for a category
mismatch — but no deer image ranked high enough to become the
fallback winner. This is a real limitation of the **simulated**
embedding (a deterministic bag-of-words hash, not true semantic
understanding — see `embedding_service.py`), not a bug in the guard
logic itself: the guard did its job and refused the wrong candidate,
it just didn't have a better one available given this post's specific
word choices. Worth re-running this eval with a real `GEMINI_API_KEY`
to see whether real embeddings resolve it.

## Honest limitations

- **Vectors stored as JSON in a plain column, not pgvector.** Fine at
  ~50 images (the design doc's own scoping decision); would need
  pgvector past a few thousand rows.
- **Embedding similarity, in simulated mode, is a bag-of-words hash**,
  not true semantic understanding. It's good enough to demonstrate
  real ranking/guard behavior (and caught two real bugs during
  testing), but a real Gemini embedding would likely improve the eval
  precision further.
- **Single-process worker thread**, same limitation as the BE-06/BE-07
  background job assignments — fine at this scale.
- **No frontend for the review workflow** — explicit non-goal from the
  Phase 1 design doc, per the brief's own scope guidance. Validated
  API endpoints (`/suggestions`, approve/reject) stand in for it.
