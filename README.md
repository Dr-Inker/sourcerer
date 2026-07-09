# sourcerer

An AI **technical-sourcing agent**. Given a sourcing brief, it discovers an engineering candidate on GitHub, researches them from public sources, and produces a **grounded, cited fit-brief plus a personalized outreach draft** — where every factual claim must point at a real piece of gathered evidence, or it doesn't get made.

**▶ Live demo — [drinkerlabs.info/sourcerer/](https://drinkerlabs.info/sourcerer/)** · pick a role, watch it run `discover → research → synthesize`, then read a grounded, cited brief: the grounding score, clickable citations, and the explicit list of things it *refused* to assert. The public demo runs over **fictional personas** (`example.com` links) so it never publishes a real person's data; point it at real GitHub users via the CLI.

> **Status: Phase 1 spine + a shipped public demo.** The end-to-end pipeline is built test-first — deterministic async, strict citation-grounding, an eval/tracing seam — and the live demo above replays cached runs the pipeline generated over fictional personas, offline (Phase 2, Increment 1). The agentic browser, parallel fan-out, human-in-the-loop review UI, and the reply-loop are deliberately deferred to later phases (see [Roadmap](#roadmap)). Nothing here over-claims to be the finished product.

## Why grounding is the point

The hard problem in automated sourcing isn't finding people — it's not making things up about them. Sourcerer's load-bearing rule:

> A claim may assert a fact **only** if its citation URL appears in the candidate's gathered evidence. Anything the model can't ground is moved to an `unverified` list — it is never presented as a claim.

The guard **fails closed**: when in doubt, a statement is demoted, never asserted. This is enforced in code (`synthesis.py`), not left to prompt discipline.

**What grounding does and does not guarantee.** The guard verifies *provenance* — that the cited source is real and was actually gathered — not *entailment*: it does not yet check that the source's **content** supports the claim's wording. A model that attaches a real repo URL to an overstated fact would still pass the membership check. Content-support verification (lexical-overlap or an LLM-judge entailment pass) is a deliberate next step, not something shipped here. Note also that `grounding_score` on a *post-guard* `Assessment` is 1.0 by construction (every surviving claim is grounded); the metric that can actually drop is `model_citation_fidelity` (`evals/scorers.py`), computed over the model's **raw** claims, which is why an `Assessment` now carries a `grounding_fidelity` field exposing how often the model fabricated a citation before the guard demoted it.

## Pipeline

```
brief ──▶ discover ──▶ research ──▶ synthesize ──▶ Assessment
          (GitHub      (top repos    (grounded,     (fit score,
           user search) + robots-     cited, with    grounded claims,
                         aware web     fail-closed    unverified[],
                         fetch)        citation       outreach draft)
                                       guard)
```

Each stage is wrapped in a trace span (`discover` / `research` / `synthesize`), and the eval scorers report what fraction of claims resolve to real evidence.

## Design

- **Every I/O dependency sits behind a `typing.Protocol` with a deterministic mock** (`GitHubClient`, `Fetcher`, `LLMClient`). The entire pipeline is unit-tested with **no network calls** — the real HTTP/LLM implementations and their mocks are interchangeable.
- **Fully async** (`async def`, `httpx.AsyncClient`).
- **Public sources only.** GitHub via its REST API; web fetches respect `robots.txt`, apply timeouts, and are guarded against SSRF: every resolved address must be globally routable (loopback/private/link-local/CGNAT/NAT64/metadata are refused), the validated IP is **pinned** to the connection (closing the DNS-rebinding gap between check and connect), and each redirect hop is re-validated and re-pinned. No LinkedIn, no ToS-violating scraping.
- **Secrets from the environment** via `python-dotenv`; never hardcoded.

## Ethics & data

This tool researches real people, so its posture matters as much as its output (full policy in the design spec, §10):

- **Public sources only, minimized.** Only GitHub's public API and a candidate's own linked blog are read; no LinkedIn, no scraping behind auth, no sensitive-category inference.
- **Grounding is a harm-reduction feature.** The fail-closed guard exists specifically so the tool does not publish invented claims about a named individual.
- **Human-in-the-loop before any outreach.** Outreach is a *draft*; nothing is sent automatically. A real deployment gates every send behind human review and a safe/opt-in inbox.
- **Deletion / takedown.** If you are shown on the demo and want to be removed, contact the maintainer (see the repo) and the entry will be taken down. The public demo is meant to move to fictional candidates; treat any real-person data there as illustrative, not an endorsement or a rating you consented to.

### Module map

| Module | Responsibility |
| --- | --- |
| `config.py` | Env-backed settings (`get_settings`) |
| `models.py` | Pydantic domain vocabulary (`Brief`, `Candidate`, `Evidence`, `EvidenceBundle`, `Claim`, `Assessment`) |
| `llm.py` | `LLMClient` protocol · `MockLLM` · `LiteLLMClient` |
| `github.py` | `GitHubClient` protocol · `MockGitHub` · `HttpGitHub` |
| `web.py` | `Fetcher` protocol · `MockFetcher` · robots-aware, SSRF-guarded `HttpFetcher` · HTML→text |
| `discovery.py` | `brief → candidates` (GitHub user search) |
| `ingest.py` | Repo-file selection + truncation for file-level grounded citations (README/notable-file picking, binary/vendored/lockfile skipping, byte budgets, blob-URL construction) |
| `research.py` | `candidate → cited EvidenceBundle` (repos + per-file evidence + blog) |
| `synthesis.py` | `evidence → grounded brief + outreach` (the fail-closed citation guard) |
| `evals/scorers.py` | `grounding_score`, `claims_resolve`, `model_citation_fidelity` |
| `trace.py` | Context-local span recorder (per-run isolated; portable seam ahead of a tracing backend) |
| `pipeline.py` | `run(brief, …)` — discover → research → synthesize, traced |
| `cli.py` | Command-line entry point |
| `demo/schema.py` | `DemoRun` artifact + `to_demo_run` — serializes a run for the static demo; dedupes repeated claims |
| `demo/generate.py` | Offline generator — runs the real pipeline over **fictional `example.com` personas** (deterministic mock clients, no keys) and writes the demo's cached JSON |

`evals/golden.json` is a small labeled seed set (`brief → expected candidate`) kept for later precision scoring; it is not yet consumed by the scorers.

## Quickstart

Requires **Python ≥ 3.12**.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest            # full suite, fully network-free
```

To run it for real against live GitHub + an LLM, copy `.env.example` to `.env` and fill it in:

```bash
cp .env.example .env
# GITHUB_TOKEN    — a GitHub token (public data only; raises the API rate limit)
# <provider> key  — match SOURCERER_MODEL's provider (LiteLLM routes by model prefix):
#                   the default openrouter/z-ai/glm-5.1 needs OPENROUTER_API_KEY;
#                   an anthropic/* model needs ANTHROPIC_API_KEY
# SOURCERER_MODEL — LiteLLM model id; defaults to openrouter/z-ai/glm-5.1
```

> The LLM is called through [LiteLLM](https://github.com/BerriAI/litellm), so `SOURCERER_MODEL` and the provider key you supply must match (e.g. the default `openrouter/z-ai/glm-5.1` needs `OPENROUTER_API_KEY`; an `anthropic/*` model needs an Anthropic-compatible key).

Then:

```bash
sourcerer "Rust systems engineer" --lang rust
# usage: sourcerer [-h] [--lang LANG] [--topic TOPIC] [-n MAX] role
#   --lang / --topic may be repeated; -n/--max caps candidates (default 1)
```

It prints each candidate with a fit score and grounding score, the grounded claims (each with its citation), anything unverified, and the outreach draft.

## Testing

```bash
pytest            # all tests; no network, deterministic
```

The suite covers each module plus an end-to-end pipeline test (all mocks), including the grounding guard's demotion of ungrounded claims and the SSRF address checks. CI runs it on every push (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Roadmap

Phase 1 is the spine; **Phase 2, Increment 1 — the public [live demo](https://drinkerlabs.info/sourcerer/)** (curated preset roles replaying real grounded runs, pure-static, no secrets on the public path) — is shipped. Still deliberately deferred to later phases (each gets its own plan):

- LangGraph orchestration + parallel research fan-out
- Agentic browser (Browser Use / Stagehand) for the open-web long tail
- Human-in-the-loop review UI + gated outreach send
- pgvector memory · hardened, authenticated MCP server
- Guardrails / prompt-injection defense (fetched pages are untrusted)
- Cost router · durable, checkpointed runs · tracing export
- The **reply-loop**: learning from replies to improve targeting and messaging

Design spec and the Phase-1 implementation plan live under [`docs/`](docs/).

## License

[MIT](LICENSE) © 2026 Dr-Inker.
