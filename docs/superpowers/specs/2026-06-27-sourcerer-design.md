# Sourcerer — design spec

> **Working name: "sourcerer"** (technical-sourcing agent; easily changed).
> An AI technical-sourcing agent: give it a role/ICP → it discovers engineering candidates from
> public signals, fans out parallel browser sub-agents to research each across the open web, writes a
> *cited* fit-brief + a personalized outreach message, and — on your per-candidate approval — sends it.
> It then **learns from replies** to improve who it targets and how it writes. Reliability is measured
> and published honestly, not assumed.

_Status: design, awaiting approval. Date: 2026-06-27._

## 1. Why this exists (origin story)
Technical sourcing is mostly manual, shallow, and spammy: recruiters blast generic InMail off a title
match. The expensive, high-signal part — actually reading someone's work and writing something they'd
reply to — is exactly what an agent that can *research the open web and take a gated action* should do.
It is a real, recognizable workflow with obvious ROI (reply rate, hours saved), it lives entirely on
**public** data, and the genuinely hard part (reliable open-web research + grounded personalization) is
where senior judgment shows.

## 2. Goals / non-goals
**Goals**
- One vertical, action-taking agent that reads as **senior/production-grade**, deployed and demoable.
- Multi-agent **where justified** (parallel candidate research), single-threaded for synthesis + the action.
- A real, **HITL-gated action** (send outreach) — reversible behind explicit human approval.
- A **closed reply-loop**: outcomes (replies) feed back into targeting + message style (online eval).
- **Honest reliability**: published per-source success rate + a failure taxonomy.
- The full operational envelope (evals, tracing, guardrails, cost routing, durability, memory, MCP).

**Non-goals (YAGNI)**
- Not an eval/verification product (that was the last project). Eval rigor lives *inside* this one.
- No LinkedIn scraping or any ToS-violating source. No bulk cold-emailing of real people.
- No ATS marketplace integrations beyond one optional sandbox writer. No multi-tenant SaaS, billing, or auth-heavy app.
- No fine-tuning (demonstrating *when not to* is itself a positive signal).

## 3. Users & the core scenario (the demo narrative)
A recruiter/founder gives a brief: _"Find 5 Rust engineers who'd be excited about systems-level AI
tooling and would actually reply."_ The agent:
1. **Discovers** candidates from GitHub (search by language/topic/contribution patterns + activity).
2. **Researches** each in parallel across the open web (GitHub profile/repos via API; personal site,
   blog, conference talks, OSS work via an agentic browser) — collecting *cited* evidence.
3. **Synthesizes** a grounded fit-brief (with explicit "couldn't verify X" honesty), a fit score, and a
   personalized outreach draft that references a specific, verifiable detail.
4. Presents each candidate in a **review UI**; the human edits/approves.
5. On approval, **sends** the outreach (demo: to a safe/test inbox).
6. **Learns**: replies (real or simulated in the demo) update the targeting model + message style.

## 4. Architecture (Approach 1+ — reliable spine, agentic where it's hard)
```
brief ─▶ Discovery (GitHub API) ─▶ Orchestrator (LangGraph)
                                      │  fan out: one Research sub-agent per candidate (parallel READS)
                                      ▼
              Research sub-agent ── GitHub API (structured)  ┐
                                 └─ Agentic browser (open web)┘─▶ cited evidence bundle
                                      │  (writes evidence to store, returns references — context engineering)
                                      ▼
                 Synthesis (single agent) ─▶ fit-brief + score + outreach draft  (grounded, cited)
                                      ▼
                 HITL review UI ─▶ approve/edit  ──▶ Action: send (Gmail/SMTP, safe target) + log
                                      ▼
                 Reply-loop: ingest reply outcomes ─▶ update targeting weights + message style (online eval)
```
**Why this shape:** deterministic where a real API exists (GitHub), agentic only for the messy open web
(no API) — the "deterministic where you can, agentic where you must" judgment. Multi-agent is used only
for the genuinely parallel **read** phase (where it earns its ~15× token cost); synthesis and the
irreversible **action** are single-threaded (where single-agent is more reliable). This is stated
explicitly because the *judgment* is the senior signal.

## 5. Components (each: purpose · interface · depends-on)
- **Discovery** — `discover(brief) -> Candidate[]`. Turns an ICP/brief into candidate seeds via the GitHub Search API + heuristics. Deps: GitHub API.
- **Orchestrator** (LangGraph graph) — owns the run: fan-out, checkpointing/resume, HITL interrupts, budget caps. Interface: `run(brief, config) -> Run`. Deps: research/synthesis nodes, store.
- **Research sub-agent** — `research(candidate) -> EvidenceBundle` (cited). Two tool backends: GitHub API (structured) + agentic browser (open web). Writes evidence to the store, returns references. Deps: browser layer, GitHub API, store.
- **Browser layer** — `browse(url|goal) -> PageEvidence`. Hybrid: deterministic Playwright for known patterns + an AI browser (Browser Use / Stagehand) for general pages; records traces; treats page content as **untrusted**. Deps: Playwright + AI-browser lib.
- **Synthesis** — `synthesize(candidate, evidence) -> Brief{rationale, score, citations, outreachDraft, unverified[]}`. Grounded; refuses to assert uncited facts. Deps: LLM via gateway.
- **HITL review UI** (thin React) — lists candidates with brief + draft; edit/approve/reject; streams the live browsing + the parallel-swarm view; shows the metrics dashboard. Deps: FastAPI.
- **Action / sender** — `send(approvedOutreach) -> SendResult`. Gmail/SMTP to a configured (safe) target; idempotent; logged. Deps: mail provider.
- **Reply-loop** — `ingest(replyEvents)`; updates targeting weights + message-style priors; exposes online metrics. Deps: store, eval module.
- **Memory** (Postgres + pgvector) — candidates, evidence, outreach, outcomes; dedupe + recall + cache. Deps: Postgres.
- **MCP server** — exposes the tools (`github_search`, `browse`, `send_outreach`, `write_record`) as a **hardened, authed** MCP server. Deps: the tools above.
- **Operational modules** — eval harness, tracing, guardrails, cost router (see §7).

## 6. The reply-loop (the bold differentiator)
Each sent outreach is tracked to an outcome: `replied(positive/negative) | no-reply(after T)`. The loop:
- **Targeting:** logistic/weighted model over candidate features (signal types that correlate with replies) → re-ranks future discovery. Starts as a transparent heuristic; upgrades to a fitted model as data grows.
- **Messaging:** maintains style/variant priors (e.g., which opening hooks get replies) and feeds them to synthesis; runs as an **online eval / bandit** over message variants.
- **Demo reality:** real reply data is slow, so the demo ships a **reply simulator** (a labeled outcome model) clearly marked as simulated, plus the wiring to ingest real replies. This is honest *and* shows the closed loop staff-level candidates are asked to design.

## 7. Operational envelope (the senior layer)
- **Eval harness** (first-class, in `evals/`): a curated golden set (~50–200 candidates/briefs) with scorers for (a) **sourcing precision** (are found candidates relevant?), (b) **brief factual-grounding** (every claim cited + verifiable; hallucination = fail — reuses the `refute` muscle), (c) **outreach quality** (LLM-judge rubric), (d) **end-to-end task success**, (e) **cost & latency per candidate**. Wired into **CI** as a regression gate; a script converts failed production traces into new eval cases (closed loop).
- **Tracing/observability:** OpenTelemetry GenAI conventions → self-hosted **Langfuse**; spans for tool-call / reasoning / browse / memory-op.
- **Guardrails / security:** fetched pages are **untrusted** → **prompt-injection defense** (the agent must resist instructions embedded in a candidate's site); PII minimization; output schema validation; least-privilege tools; HITL before any send. A scripted indirect-injection test is part of the demo.
- **Cost routing:** all model calls via a **LiteLLM** gateway with provider fallback, a hard budget cap, prompt caching, and cheap-model routing for low-stakes steps; per-run cost surfaced in the UI.
- **Durability:** LangGraph checkpointer on Postgres; resume-from-failure; idempotency keys on sends.
- **Reliability measurement (the differentiator):** per-source browser **success rate** + a documented **failure taxonomy** (timeouts, anti-bot, layout-misread, ambiguous-match, injection-attempt), published in the README.

## 8. Wow / demo design (built in, no added fragility)
1. **Watchable live browsing** — stream the agent navigating real sites + reasoning.
2. **Visualized parallel research swarm** — watch N sub-agents research candidates concurrently (the correct architecture, made visible).
3. **Uncanny personalization** — outreach cites a specific verifiable detail it dug up.
4. **Autonomy span** — vague brief in → ready-to-send outreach out.
5. **Honest live metrics** — real success rate + failure taxonomy + per-run cost on screen.
6. (**reply-loop**) — a before/after showing targeting + messaging improving from outcomes.

## 9. Stack
Python (primary) · LangGraph (orchestration) · Browser Use / Stagehand on Playwright (agentic browser) ·
GitHub REST/GraphQL API · Postgres + pgvector · FastAPI · thin React/TS UI · LiteLLM (gateway) ·
Langfuse (tracing/evals) · Docker · deploy on Fly.io. LLMs via OpenRouter/Gemini (cross-provider).

## 10. Data, legal & ethics (a senior signal in itself)
- **Public sources only**, accessed compliantly: GitHub via its **API** (within ToS + rate limits); open web via browser respecting `robots.txt` and rate limits. **No LinkedIn / no ToS-violating scraping.**
- **Personal data minimization:** store only what's needed; support deletion; no sensitive categories; a short GDPR/personal-data note.
- **Anti-spam:** the demo sends only to a **safe/test inbox**; never bulk-cold-emails real people; per-send HITL approval is mandatory.

## 11. Scope & milestones (4–8 weeks, solo)
- **Wk 1–2 — vertical slice:** discovery (GitHub) → research one candidate (API + one browser source) → grounded synthesis → eval harness skeleton + tracing. *Gate: one end-to-end candidate with a cited brief, measured.*
- **Wk 3–4 — breadth + action:** parallel orchestration; open-web browsing; HITL review UI (with live-browse + swarm view); HITL-gated send. *Gate: brief → 5 candidates → approved send, on a deployed instance.*
- **Wk 5–6 — operational envelope:** guardrails + injection defense, cost router, durability/resume, MCP server, reliability measurement + failure taxonomy.
- **Wk 7 — reply-loop:** outcome ingestion + targeting/messaging update + online metrics (with the simulator).
- **Wk 8 — polish + story:** deploy, demo video, README + an honest teardown post (architecture, eval numbers, reliability + failure taxonomy, multi-agent cost/benefit, what I'd do next).

## 12. Risks & mitigations
- **Open-web browsing is unreliable (the category's whitespace).** → Don't claim robust autonomy; *measure* it, narrow the happy path, fall back to deterministic Playwright + API, and make honest metrics the headline.
- **Scope creep across the full envelope in a few weeks.** → Phase-gate; the load-bearing three (eval, tracing, HITL) first; reply-loop is week 7, droppable to a stretch if behind.
- **Anti-bot / rate limits.** → API-first; managed browser/anti-bot only if needed ($20–99/mo); cache aggressively.
- **Ethics/legal optics of "researching people."** → public-only, minimized, deletable, demo-to-safe-inbox; documented.

## 13. Success criteria
- Deployed, runnable demo (URL) + a public repo a senior reviewer scans in 5 min and sees: traces, an `evals/` folder gated in CI, guardrails + an injection test, a cost dashboard, durable runs, a custom MCP server, and **honest reliability numbers**.
- A brief → 5 researched, cited, personalized, human-approved, sent outreaches — end to end.
- A documented reply-loop improving targeting/messaging on outcome data.
- A teardown write-up that demonstrates *judgment* (when multi-agent helps, what failed, what it cost).
