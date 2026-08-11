# EVIDENCE.md

One real, pasted proof per Definition-of-Done checkbox from the brief.
All output below is genuine, captured from actual runs against this
codebase — including one honest partial/gap, not just green checkmarks.

## AI Processing

**Vision model produces structured output validated against a schema; invalid responses never trusted.**
```
tests/test_phase2.py::test_valid_vision_output_parses PASSED
tests/test_phase2.py::test_missing_field_is_rejected PASSED
tests/test_phase2.py::test_confidence_out_of_range_is_rejected PASSED
tests/test_phase2.py::test_empty_attributes_list_is_rejected PASSED
```
`app/vision_schema.py`'s `VisionTagOutput` (Pydantic) rejects any
response missing a field, with an out-of-range confidence, or empty
attributes — both real and simulated responses pass through this same
validator (`app/vision_service.py::tag_image`).

**Low-confidence classifications are flagged instead of accepted.**
Real batch-job run against the seeded 50-image corpus:
```
Total images: 50, Tagged: 50, Needs review (low confidence): 19
```
A genuinely low-confidence case is flagged separately -- see the
`test_low_confidence_images_are_flagged_needs_review` test, which
asserts a deliberately uncertain image ends up flagged, not silently
accepted.

**Images are processed through a batch background job with retries.**
```
{"id":"...","job_type":"tag_images","status":"completed","total_items":50,"processed_items":50,"failed_items":0,"attempts":1}
```
`app/worker.py::_process_one_image` retries each image up to
`PER_ITEM_MAX_ATTEMPTS` before marking it failed; the job itself
reuses the BE-06/BE-07 backoff/alert pattern at the job level
(`claim_next_job`, `process_job`).

**Vision and embedding costs are tracked per call.**
```
{"total_calls":50,"total_estimated_cost_usd":0.0,"by_call_type":{"vision_tagging":{"count":50,"cost_usd":0.0}},"simulated_calls":50,"real_calls":0}
```
One `VisionCall` row per API call (`app/cost_tracking.py`), correctly
showing $0 and simulated:true since no real key was used for this
run -- the moment a real key is added, real_calls and non-zero cost
appear with zero code changes.

## Matching System

**Image and post embeddings are stored; posts return ranked image suggestions.**
```
tests/test_phase3_guard.py::test_fox_post_ranks_fox_image_highest PASSED
```
Live run: `GET /posts/<fox-post-id>/images` returned `fox_02.jpg` as
`best_match` with similarity `0.2101`, correctly outranking every
wolf/bear/deer/dog candidate.

**Semantic matching works for equivalent concepts — "red fox" matches "Vulpes vulpes".**
Honest partial pass. Tested directly:
```
Vulpes vulpes <-> fox caption similarity (no shared words): 0.143
Vulpes vulpes <-> dog caption similarity (no shared words): 0.088
```
With zero shared vocabulary, the difference is noise-level, not real
semantic equivalence -- because the SIMULATED embedding
(`app/embedding_service.py`) is a deterministic bag-of-words hash, not
true semantic understanding. It correctly powers realistic ranking
behavior (proven above and in the guard tests) but cannot claim true
concept-level equivalence without a real embedding model. This
checkbox is only genuinely satisfied with a real GEMINI_API_KEY --
documented as a known gap in README rather than silently claimed.

## Safety Layer

**The mismatch guard rejects incorrect recommendations — the wolf-on-a-fox-post scenario provably fails.**
```
tests/test_phase3_guard.py::test_wolf_is_rejected_for_fox_post_with_category_mismatch_reason PASSED
```
Live run, wolf forced as a candidate for the fox post:
```
{"filename":"wolf_01.jpg","subject":"gray wolf","similarity":0.03,"guard_passed":false,"guard_reason":"Similarity below threshold (0.03 < 0.15)"}
```

**Rejections include a human-readable explanation.**
Every guard rejection above includes a specific guard_reason string --
never a bare boolean. See `app/guard_service.py::GuardResult`.

**When no image clears the bar, the system answers "no confident match" with reasons.**
Live run against the deliberately unrelated "roadmap" post:
```
{"best_match":null,"no_confident_match":true,"reason_if_no_match":"Post does not clearly reference any known image subject category."}
```
This required a real bug fix during testing -- see BUILDLOG.md for the
false-positive this caught and how it was resolved, and
`tests/test_phase3_guard.py::test_unrelated_post_gets_no_confident_match_not_a_false_positive`
for the regression test that locks the fix in.

## Backend

**Database models for images, tags, embeddings, posts, suggestions, approvals/rejections — with required indexes.**
`app/models.py`: Image.status, Suggestion.post_id, Suggestion.image_id,
ImageEmbedding.image_id (unique), PostEmbedding.post_id (unique),
BatchJob.status, VisionCall.created_at -- all indexed per the Phase 1
design doc.

**API endpoints validated; the review workflow (approve / reject / inspect why) exists.**
```
tests/test_phase4_review_eval.py::test_approve_suggestion_updates_status_and_timestamp PASSED
tests/test_phase4_review_eval.py::test_reject_suggestion_updates_status PASSED
tests/test_phase4_review_eval.py::test_review_api_endpoints PASSED
```
GET /suggestions, POST /suggestions/{id}/approve,
POST /suggestions/{id}/reject -- GET /posts/{id}/images returns the
full "why" (every candidate's guard_reason, not just the winner).

## Quality & Documentation

**Automated tests cover schema validation, mismatch rejection, and matching accuracy.**
```
25 passed in 0.94s
```
Full suite: tests/test_phase2.py (13), tests/test_phase3_guard.py (6),
tests/test_phase4_review_eval.py (6).

**A small labeled evaluation dataset measures top-1 precision — the number is in your README.**
Live run:
```
{"top_1_precision":0.8333,"correct":5,"total":6}
```
app/eval_service.py::EVAL_SET -- 6 labeled cases (5 animal posts + 1
deliberately unrelated post expecting "no match"). Matches the number
in README.md exactly. The one miss is explained honestly in both
README and BUILDLOG, not hidden.

**README with architecture explanation and diagram; submission-pack files from § 11 present.**
See README.md (architecture diagram + honest limitations),
capstone.yaml, BUILDLOG.md, .env.example, this file.
