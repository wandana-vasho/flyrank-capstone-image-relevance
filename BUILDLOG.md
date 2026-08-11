# BUILDLOG.md — AI usage, honestly

Built in collaboration with Claude (Anthropic). Per the brief: "keep
BUILDLOG.md honest — where AI helped, where it was wrong, what you
changed." Below is exactly that, not a sanitized version.

## Where AI helped

- **Phase 1 design doc and overall architecture** — the layer split
  (HTTP → service → repository/model, with matching and guarding kept
  as two separate modules) was proposed by Claude and reviewed against
  the brief's rubric ("swap the DB or a provider without touching
  business logic") before any code was written.
- **Boilerplate**: SQLAlchemy models, Pydantic schemas, FastAPI route
  wiring — genuinely repetitive, low-risk code.
- **The simulated vision/embedding fallback design** — letting the
  whole system run and be genuinely tested at $0, with a real API key
  swapping in later touching only two files. I need to be able to
  explain why the simulator is filename-hinted (vision) and
  bag-of-words-hashed (embeddings) rather than pure random noise, and
  what its real limitation is (see below).

## Where AI was wrong — and caught by actually testing, not just reading code

- **Similarity threshold miscalibrated on the first attempt.** The
  guard's SIMILARITY_THRESHOLD was initially set to 0.25 without first
  checking what range the simulated embeddings actually produce.
  Running the real fox-post demo scenario showed the correct fox match
  scored 0.21 — below that threshold — so even the right answer got
  rejected. Caught by running the actual demo probe, not by inspecting
  the code. Recalibrated to 0.15 based on real observed output.
- **A real false positive in the "no confident match" case.** Testing
  the deliberately-unrelated "roadmap" post against the corpus, the
  guard incorrectly accepted a deer image at 0.26 similarity — pure
  embedding hash-collision noise, not a real match. This is
  significant: it's exactly the failure mode the mismatch guard exists
  to prevent, and it slipped through on the first implementation. The
  fix: the category cross-check was originally exclusionary only (only
  rejects if a known subject was detected AND it mismatched); it now
  runs first and is a required positive signal — if the post can't be
  tied to any known corpus subject at all, that's an automatic refusal
  regardless of how high the similarity score looks. A regression test
  (test_unrelated_post_gets_no_confident_match_not_a_false_positive)
  locks this fix in.
- **A test assertion bug, not a code bug.** One eval test compared the
  rounded top_1_precision (intentionally rounded to 4 decimals in
  eval_service.py) against the unrounded fraction with a far tighter
  tolerance than the rounding itself introduces. Fixed the test's
  assertion, not the eval logic, once the actual AssertionError output
  made clear which side was wrong.

## What I changed / verified myself

- Every claim in EVIDENCE.md is backed by output I actually ran and
  captured — the batch job JSON responses, the eval script's real
  output, the exact test names and pass counts — not paraphrased or
  invented.
- I deliberately did NOT claim the "semantic equivalence" checkbox
  (red fox / Vulpes vulpes) as fully passing. I tested it directly
  with zero shared vocabulary between the two texts and got a
  noise-level, not meaningful, similarity difference — because the
  simulated embedding is a bag-of-words hash, not true semantic
  understanding. This is documented as an honest partial-pass in
  EVIDENCE.md and README, not silently claimed as done. A real
  GEMINI_API_KEY would need to be used to genuinely verify this
  requirement.
- The eval's one real miss (the deer post) is left in the reported
  number rather than adjusted away — 83.33%, not a rounded-up or
  cherry-picked figure.

## What I can explain at the demo

If asked to walk through 2-3 specific lines:
1. Why evaluate_candidate checks category BEFORE similarity, not
   after — and the specific false positive that made that ordering
   necessary, not just a stylistic choice.
2. Why _infer_expected_subject pulls from Image.subject values already
   in the database rather than a hardcoded animal list — so the
   guard's category logic is generic to whatever corpus this system is
   pointed at, not hand-tuned to fox/wolf/dog/bear/deer specifically.
3. Why the vision tagging's per-item retry (inside _process_one_image)
   is separate from the batch job's own job-level retry/backoff — a
   single bad image shouldn't take down or delay retrying a 50-image
   batch.
