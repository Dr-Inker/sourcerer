# Sourcerer — Phase 2, Increment 1: Public demo at drinkerlabs.info/sourcerer/

**Status:** Design approved 2026-06-27. Successor work to the [Phase-1 vertical slice](2026-06-27-sourcerer-design.md) (the `discover → research → synthesize` pipeline with fail-closed citation grounding, shipped and merged).

**Goal:** Put a *usable, visible* Sourcerer on the portfolio site that foregrounds its differentiator — **honest, grounded, cited candidate briefs** — without exposing live compute, secrets, or an abuse surface on the public server.

## Decisions (locked during brainstorming)

1. **Input model = curated presets only.** Visitors pick from ~4 pre-vetted roles; no free-text. (Free-text is a deliberately deferred later increment.)
2. **Execution model = precomputed, replayed.** The real pipeline runs **offline** to produce a cached result per preset; the public page replays it. Consequence: **no live API calls, no secrets, no rate-limiting, and no SSRF/abuse surface on the public path.**
3. **Hosting = pure static**, served from the existing webroot `/var/www/drinkerlabs/sourcerer/` exactly like the homepage and `/game/`. **No backend service, no loopback port, no nginx proxy.** (A FastAPI service was considered and rejected — it adds a systemd unit, a port, and a proxy for content that is static.)
4. **Read-only.** No outreach is sent. The draft is shown as a deliverable. (HITL approve-and-send is a later authenticated increment, never on the public demo.)

## What the visitor sees

Pick a preset role → a **stage-by-stage replay animation** (`discover → research → synthesize`, timed from the recorded trace spans, so it reads as "watching it work") → then the result, which foregrounds the grounding story:

- **Fit score** and **grounding score** (fraction of claims that resolve to real evidence).
- **Grounded claims**, each with a **clickable citation link** to the real GitHub repo / blog it came from.
- **The `unverified` list** — *what the agent refused to assert* because it could not ground it. This is the differentiator made visible.
- **The outreach draft.**
- A short "how it works / why grounding matters" explainer, a link to the **GitHub repo** (so anyone can run it live themselves), and a **"cached sample run, generated `<timestamp>`"** label so it is honestly presented.

The page matches the site's existing look (neon Dr-Inker theme, self-hosted fonts, dark palette).

## Architecture

Three well-bounded units plus deploy glue. The existing Phase-1 package (`sourcerer.pipeline`, `sourcerer.evals.scorers`, `sourcerer.trace`, the domain models) is reused unchanged.

### Unit 1 — Demo result schema + serializer (`src/sourcerer/demo/schema.py`)
- **Does:** defines a `DemoRun` pydantic model — the single artifact the page consumes — and a pure function `to_demo_run(brief, assessment, bundle, spans, model, generated_at) -> DemoRun`.
- **`DemoRun` shape:** `role`, `languages`, `candidate` (login, name, profile_url), `fit_score`, `grounding_score`, `claims: [{text, citation}]`, `unverified: [str]`, `outreach_draft`, `evidence: [{kind, source_url, text}]` (mirrors the `Evidence` model, for a "sources" list; the page may truncate `text` for display), `spans: [{name, ms, ok}]` (for the replay), `model`, `generated_at` (ISO string).
- **Depends on:** `sourcerer.models`, `sourcerer.evals.scorers`. No I/O. **Fully unit-testable with a mocked pipeline result.**
- **Interface:** `DemoRun.model_dump_json()` is the on-disk/over-the-wire format.

### Unit 2 — Offline generator (`src/sourcerer/demo/generate.py`, run as `python -m sourcerer.demo.generate`)
- **Does:** holds the curated preset list; for each preset, builds the **real** clients (`HttpGitHub`, `HttpFetcher`, `LiteLLMClient`) from `config`, runs the pipeline (`reset_spans()` → `run(...)` → `get_spans()`), computes `grounding_score`, calls `to_demo_run(...)`, and writes `web/demo/<slug>.json`. Also writes `web/demo/manifest.json` listing the presets (`{slug, label, role, languages}`).
- **Curated presets (draft):** Rust systems engineer (`rust`) · React/TypeScript frontend (`typescript`) · ML infra / PyTorch (`python`) · Go distributed systems (`go`).
- **Depends on:** the whole Phase-1 pipeline + real network + `OPENROUTER_API_KEY` and `GITHUB_TOKEN` in `/opt/sourcerer/.env`. This is the **only** place real keys/network are used. Not unit-tested (it makes live calls); its pure core (`to_demo_run`) is.
- **`timestamp` note:** `generated_at` is passed in by the caller (the CLI stamps it), since the pipeline forbids wall-clock inside itself.

### Unit 3 — Static page (`web/index.html`, `web/sourcerer.css`, `web/sourcerer.js`)
- **Does:** plain HTML/CSS/vanilla JS (no build step, matching the homepage). On load, fetches `demo/manifest.json` and renders the preset chooser. On select, fetches `demo/<slug>.json`, plays the span-timed replay animation (durations normalized/capped so it stays snappy), then renders scores, claims-with-citations, the unverified list, the outreach draft, the sources list, and the explainer/repo-link/timestamp.
- **Depends on:** only the JSON artifacts. Degrades gracefully when a `demo/*.json` is missing (shows a "sample not generated yet" placeholder) so the committed page works before generation.

### Deploy glue (`deploy/deploy-demo.sh` + a `web/README.md`)
- **Does:** runs the generator (one-time/whenever refreshing), then copies `web/` → `/var/www/drinkerlabs/sourcerer/`. Documents the nginx check (the catch-all `location /` should serve the new subdir and `.json` with the right content-type — expected to need **no** nginx change; verify before relying on it).

## Data flow

```
offline (this box, with keys):
  presets → pipeline.run(real clients) → (Assessment, EvidenceBundle) + spans
          → to_demo_run() → web/demo/<slug>.json   (+ manifest.json)
  deploy-demo.sh → copy web/ → /var/www/drinkerlabs/sourcerer/

public (no compute, no secrets):
  browser → GET /sourcerer/ (static index.html/css/js)
          → GET /sourcerer/demo/manifest.json
          → on click: GET /sourcerer/demo/<slug>.json → replay + render
```

## Security / abuse posture

- **No live compute on the public path** — only static files. No secrets reach the public-facing server process (there isn't one beyond nginx).
- **No new attack surface** beyond serving static `.html`/`.css`/`.js`/`.json` from a directory nginx already serves.
- **SSRF** is only in play during *offline* generation, where the Phase-1 robots-aware, private-IP-guarded `HttpFetcher` already applies.
- Results are **labeled as cached samples** with a generation timestamp; the repo link lets anyone reproduce them — honest by construction.

## Testing

- **Unit:** `to_demo_run()` over a hand-built `(Assessment, EvidenceBundle, spans)` fixture (network-free) — asserts the `DemoRun` JSON carries claims-with-citations, the unverified list, both scores, and the spans. Added to the existing pytest suite; **CI stays green** (no network).
- **Generator & page:** verified manually (the generator makes live calls; the page is a static artifact). Not in CI.

## Files

- Add: `src/sourcerer/demo/__init__.py`, `src/sourcerer/demo/schema.py`, `src/sourcerer/demo/generate.py`, `tests/test_demo_schema.py`, `web/index.html`, `web/sourcerer.css`, `web/sourcerer.js`, `web/README.md`, `deploy/deploy-demo.sh`.
- Generated (git-ignored): `web/demo/*.json`, `web/demo/manifest.json`.
- No changes to the Phase-1 pipeline modules.

## Dependency / risk

Generating **real** cached results requires `OPENROUTER_API_KEY` + `GITHUB_TOKEN` in `/opt/sourcerer/.env`. If present, real runs are generated during the build. If absent, the page ships wired-up with the graceful "not generated yet" placeholder and is regenerated the moment keys are available. **Results are never fabricated** — real grounding is the entire point.

## Out of scope (explicit later increments)

Live "re-run" button · free-text role input · HITL review + outreach send · and the rest of the Phase-2 backlog (LangGraph parallel fan-out, agentic browser, pgvector memory, MCP server, reply-loop, cost router, Langfuse export).

## Done =

`/sourcerer/` is live on drinkerlabs.info: a visitor picks a preset, watches the staged replay, and sees a grounded, cited brief + outreach draft with the grounding score and the explicit "unverified" list — all static, with real cached results (once keys are available), and the unit test for the serializer green in CI.
