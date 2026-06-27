# sourcerer

An AI **technical-sourcing agent**. Given a sourcing brief, it discovers an engineering candidate on GitHub, researches them from public sources, and produces a **grounded, cited fit-brief plus a personalized outreach draft** — where every factual claim must point at a real piece of gathered evidence, or it doesn't get made.

> **Status: Phase 1 — vertical slice.** This is the end-to-end spine built test-first: a deterministic async pipeline with strict citation-grounding and an eval/tracing seam. The agentic browser, parallel fan-out, human-in-the-loop review UI, and the reply-loop are deliberately deferred to later phases (see [Roadmap](#roadmap)). Nothing here over-claims to be the finished product.

## Why grounding is the point

The hard problem in automated sourcing isn't finding people — it's not making things up about them. Sourcerer's load-bearing rule:

> A claim may assert a fact **only** if its citation URL appears in the candidate's gathered evidence. Anything the model can't ground is moved to an `unverified` list — it is never presented as a claim.

The guard **fails closed**: when in doubt, a statement is demoted, never asserted. This is enforced in code (`synthesis.py`) and checked by the eval scorers, not left to prompt discipline.

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
- **Public sources only.** GitHub via its REST API; web fetches respect `robots.txt`, apply timeouts, and are guarded against SSRF (private/loopback/link-local/metadata addresses are refused, with per-hop redirect validation). No LinkedIn, no ToS-violating scraping.
- **Secrets from the environment** via `python-dotenv`; never hardcoded.

### Module map

| Module | Responsibility |
| --- | --- |
| `config.py` | Env-backed settings (`get_settings`) |
| `models.py` | Pydantic domain vocabulary (`Brief`, `Candidate`, `Evidence`, `EvidenceBundle`, `Claim`, `Assessment`) |
| `llm.py` | `LLMClient` protocol · `MockLLM` · `LiteLLMClient` |
| `github.py` | `GitHubClient` protocol · `MockGitHub` · `HttpGitHub` |
| `web.py` | `Fetcher` protocol · `MockFetcher` · robots-aware, SSRF-guarded `HttpFetcher` · HTML→text |
| `discovery.py` | `brief → candidates` (GitHub user search) |
| `research.py` | `candidate → cited EvidenceBundle` (repos + blog) |
| `synthesis.py` | `evidence → grounded brief + outreach` (the fail-closed citation guard) |
| `evals/scorers.py` | `grounding_score`, `claims_resolve` |
| `trace.py` | In-memory span recorder (portable seam ahead of a tracing backend) |
| `pipeline.py` | `run(brief, …)` — discover → research → synthesize, traced |
| `cli.py` | Command-line entry point |

`evals/golden.json` is a small labeled seed set (`brief → expected candidate`) kept for later precision scoring; it is not yet consumed by the scorers.

## Quickstart

Requires **Python ≥ 3.12**.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest            # 21 tests, fully network-free
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

Phase 1 is the spine. Deliberately deferred to later phases (each gets its own plan):

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
