# Current implementation status

This document describes the shipped code as of 2026-07-27. The dated specifications and plans under `docs/superpowers/` remain historical records; where they conflict with this document or the root README, the current code and this document take precedence.

## Shipped

- Brief-aware GitHub discovery using role, languages, topics, and must-have terms.
- A larger recall pool reranked deterministically against full GitHub profile text.
- Public profile, repository, selected repository-file, and linked-blog evidence.
- Forked and archived repositories excluded from skill evidence; uncertain ownership is labeled explicitly.
- Strict domain and LLM-output validation with bounded inputs and HTTP(S)-only evidence URLs.
- Fail-closed claim validation requiring both a gathered citation URL and a non-trivial verbatim excerpt found in that evidence.
- Unsupported claims demoted to `unverified`; an assessment with no surviving claims receives a zero fit score and no outreach draft.
- Outreach rebuilt deterministically from a surviving claim, preventing model-authored prose from bypassing grounding.
- Bounded concurrent candidate research and synthesis.
- `run_detailed` results containing successful assessments and typed, stage-specific candidate failures; `run` remains the compatibility API.
- SSRF-resistant, robots-aware web fetching with DNS validation, IP pinning, redirect revalidation, and conservative address classification.
- A fictional, static public demo exposing citation resolution, exact quote support, model citation fidelity, supporting excerpts, and evidence.
- Network-free tests, an 80% coverage floor, Ruff linting, and a deterministic retrieval gate enforced by CI.

## Metric interpretation

- `grounding_score`: fraction of surviving claims whose citations resolve to gathered evidence. Empty assessments score zero.
- `quote_support_score`: fraction of surviving claims whose exact supporting excerpt occurs in the cited evidence.
- `grounding_fidelity`: fraction of the model's raw asserted claims that cited a gathered URL before the fail-closed guard.
- Retrieval MRR/top-1: regression results over the small deterministic golden set in `evals/golden.json`; these are not real-world recruiting-quality estimates.

Exact quote support is stronger than URL membership, but it is not semantic entailment. A genuine excerpt can still be interpreted too broadly.

## Deliberately not claimed

- Validated real-world sourcing precision or recall.
- Semantic entailment of every claim.
- Calibrated or bias-audited fit scores.
- Commit/PR-level authorship attribution.
- Automated outreach delivery.
- Durable checkpoints, retries/backoff, persistent storage, or tracing export.
- Production cost, latency, fairness, or recruiter-utility benchmarks.

Those require human-labeled datasets and operational evidence. They remain release gates rather than inferred accomplishments.

## Quality gate

```bash
pytest --cov=sourcerer --cov-report=term-missing --cov-fail-under=80 -q
ruff check src tests
python -m sourcerer.evals.run --min-mrr 0.8
node --check web/sourcerer.js
```
