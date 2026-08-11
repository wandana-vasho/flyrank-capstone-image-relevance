# DEMO_SCRIPT.md — the 6-minute live demo

Rehearsal script following the capstone brief's § 13 flow exactly, using
real endpoints already verified working in this build.

## Setup before the demo starts

```bash
rm -f image_relevance.db
python corpus/download_corpus.py
python seed.py
python -m uvicorn main:app --reload
```

Note the fox post's and the roadmap post's IDs ahead of time:
```bash
python3 -c "
from app.models import SessionLocal, Post
db = SessionLocal()
for p in db.query(Post).all():
    print(p.id, '-', p.title)
db.close()
"
```

## The flow

**1. Show images being processed — tags and captions appearing automatically**
```bash
curl -X POST "http://localhost:8000/batch-jobs/tag-images?idempotency_key=demo-tag"
curl "http://localhost:8000/batch-jobs/<job-id>"
curl "http://localhost:8000/images?needs_review=true"
```
> "50 images, one batch job. About a fifth got flagged for low
> confidence instead of silently trusted — that's the point."

**2. Open the red fox article -> fox surfaces on top**
```bash
curl -X POST "http://localhost:8000/batch-jobs/embed-images?idempotency_key=demo-embimg"
curl -X POST "http://localhost:8000/batch-jobs/embed-posts?idempotency_key=demo-embpost"
curl "http://localhost:8000/posts/<fox-post-id>/images"
```
> "best_match is a real fox image, similarity 0.21, passed every check
> in the guard. Every wolf/bear/deer/dog candidate ranks lower and is
> individually marked why."

**3. Force the wolf recommendation -> the guard refuses it**
Point at the wolf entry in the same response:
```json
{"filename":"wolf_01.jpg","subject":"gray wolf","similarity":0.03,
 "guard_passed":false,"guard_reason":"Similarity below threshold (0.03 < 0.15)"}
```
> "The guard tells you exactly why, in a sentence, not a status code."

**4. A post where nothing fits -> "no confident match"**
```bash
curl "http://localhost:8000/posts/<roadmap-post-id>/images"
```
> "best_match is null. no_confident_match is true. Reason: 'Post does
> not clearly reference any known image subject category.' It's not
> guessing."

**5. Approve one, reject another -> the review trail records both**
```bash
curl "http://localhost:8000/suggestions?status=suggested"
curl -X POST "http://localhost:8000/suggestions/<id-1>/approve"
curl -X POST "http://localhost:8000/suggestions/<id-2>/reject"
```
> "Both decisions are recorded with a timestamp -- a real audit trail."

**6. Close with the eval number**
```bash
curl -X POST "http://localhost:8000/eval/run"
```
> "Top-1 precision: 83.33%. Five of six correct, and I know exactly
> which one missed and why -- it's in the README, not just claimed."

**7. Final line**
> "Good suggestions when confident, safe rejection when uncertain --
> that's production AI."

## The one failure I'll show live

**Choice: the wolf rejection (step 3).** Deterministic in simulated
mode, directly visible in the same response as the fox success, and
it's the exact scenario the brief's own example is built around.

## Anticipated questions (from BUILDLOG.md)

1. Why does evaluate_candidate check category BEFORE similarity, not
   after -- and what specific false positive made that ordering
   necessary?
2. Why does _infer_expected_subject pull from the database's own
   Image.subject values instead of a hardcoded animal list?
3. Why is the per-image retry inside _process_one_image separate from
   the batch job's own job-level retry/backoff?
4. Why is the "semantic equivalence" checkbox an honest partial-pass
   rather than fully done? (Tested directly with zero shared
   vocabulary, got noise-level similarity -- the simulated bag-of-words
   embedding can't do true concept matching; a real Gemini key would
   be needed to verify it properly.)
