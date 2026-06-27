# Sourcerer Phase-2 Increment 1 — Public demo at /sourcerer/ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a pure-static, precomputed-replay demo of the Sourcerer pipeline at `drinkerlabs.info/sourcerer/` that foregrounds grounded, cited candidate briefs — with no live compute, secrets, or abuse surface on the public path.

**Architecture:** Reuse the shipped Phase-1 pipeline unchanged. Add a `sourcerer.demo` package: a pure `DemoRun` schema + serializer, and an offline generator that runs the real pipeline per curated preset and writes JSON artifacts. A dependency-free static page (`web/`) replays those artifacts with a staged animation and renders the grounding story. A deploy script publishes `web/` to the existing webroot.

**Tech Stack:** Python 3.12 · pydantic v2 (reused) · the existing `sourcerer` package · plain HTML/CSS/vanilla JS (no build step) · pytest + pytest-asyncio (network-free). Spec: `docs/superpowers/specs/2026-06-27-sourcerer-phase2-demo-design.md`. Branch: `phase2-demo`.

## Global Constraints
- Python ≥ 3.12; all pipeline I/O async (reused). Run tests with `/opt/sourcerer/.venv/bin/python -m pytest`; `asyncio_mode = "auto"` is already set.
- **Every new test is network-free** (mocks only) so CI stays green. The only code that makes real calls is the generator's `main()` entrypoint, which is NOT unit-tested.
- **Do not modify the Phase-1 pipeline modules** (`pipeline/discovery/research/synthesis/github/web/llm/models/trace/evals`). The demo layer only consumes them.
- The new package is `src/sourcerer/demo/` — **never** name a module `web.py` (that is the Fetcher). Static front-end assets live in the repo-root `web/` directory (committed); generated JSON lives in `web/demo/` (git-ignored).
- `run(brief, gh, fetcher, llm, model)` returns `list[tuple[Assessment, EvidenceBundle]]` (post-Phase-1 fix wave). The default model is `openrouter/z-ai/glm-5.1`.
- Results are never fabricated. The generator produces real cached runs (needs `OPENROUTER_API_KEY` + `GITHUB_TOKEN`); the page degrades gracefully when an artifact is absent.
- Repo URL used in the page: `https://github.com/Dr-Inker/sourcerer`.

## File Structure
- `src/sourcerer/demo/__init__.py` — package marker
- `src/sourcerer/demo/schema.py` — `DemoRun` model + `to_demo_run(...)` (pure)
- `src/sourcerer/demo/generate.py` — presets, `preset_to_brief`, `build_manifest`, `generate_one`, `write_demo`, `main`
- `tests/test_demo_schema.py`, `tests/test_demo_generate.py`
- `web/index.html`, `web/sourcerer.css`, `web/sourcerer.js`, `web/README.md`
- `web/demo/*.json` — generated, git-ignored
- `deploy/deploy-demo.sh` — generate + publish to webroot
- Modify: `.gitignore` (add `web/demo/`)

---

### Task 1: `DemoRun` schema + serializer (pure, TDD)

**Files:**
- Create: `src/sourcerer/demo/__init__.py`, `src/sourcerer/demo/schema.py`
- Test: `tests/test_demo_schema.py`

**Interfaces:**
- Consumes: `sourcerer.models` (`Brief`, `Candidate`, `Evidence`, `EvidenceBundle`, `Claim`, `Assessment`), `sourcerer.evals.scorers.grounding_score`.
- Produces: `DemoRun` (pydantic) and `to_demo_run(brief: Brief, assessment: Assessment, bundle: EvidenceBundle, spans: list[dict], model: str, generated_at: str) -> DemoRun`.

- [ ] **Step 1: Create the empty package marker**

Create `src/sourcerer/demo/__init__.py` (empty file).

- [ ] **Step 2: Write the failing test**

```python
# tests/test_demo_schema.py
import json
from sourcerer.models import Brief, Candidate, Evidence, EvidenceBundle, Claim, Assessment
from sourcerer.demo.schema import to_demo_run, DemoRun


def _fixture():
    cand = Candidate(login="rustdev", name="Rusty", profile_url="https://github.com/rustdev")
    bundle = EvidenceBundle(candidate=cand, items=[
        Evidence(source_url="https://github.com/rustdev/fastdb", kind="github_repo",
                 text="fastdb (Rust, ★900): embedded db"),
        Evidence(source_url="https://rusty.dev", kind="web_page",
                 text="Rusty: I build embedded Rust databases"),
    ])
    assessment = Assessment(
        candidate=cand, fit_score=0.92,
        claims=[Claim(text="Authored fastdb", citation="https://github.com/rustdev/fastdb")],
        unverified=["Worked at BigCo"], outreach_draft="Hi Rusty",
    )
    brief = Brief(role="Rust systems engineer", languages=["rust"])
    spans = [
        {"name": "discover", "ms": 12.0, "ok": True},
        {"name": "research", "ms": 30.0, "ok": True},
        {"name": "synthesize", "ms": 50.0, "ok": True},
    ]
    return brief, assessment, bundle, spans


def test_to_demo_run_captures_grounding_and_replay_fields():
    brief, assessment, bundle, spans = _fixture()
    run = to_demo_run(brief, assessment, bundle, spans,
                      model="openrouter/z-ai/glm-5.1", generated_at="2026-06-27T12:00:00Z")
    assert run.role == "Rust systems engineer"
    assert run.languages == ["rust"]
    assert run.candidate.login == "rustdev"
    assert run.fit_score == 0.92
    assert run.grounding_score == 1.0  # the sole claim's citation is in the bundle
    assert run.claims[0].citation == "https://github.com/rustdev/fastdb"
    assert run.unverified == ["Worked at BigCo"]
    assert [s.name for s in run.spans] == ["discover", "research", "synthesize"]
    assert len(run.evidence) == 2 and run.evidence[0].kind == "github_repo"
    assert run.model == "openrouter/z-ai/glm-5.1"
    assert run.generated_at == "2026-06-27T12:00:00Z"


def test_demo_run_json_round_trips():
    brief, assessment, bundle, spans = _fixture()
    run = to_demo_run(brief, assessment, bundle, spans, model="m", generated_at="t")
    data = json.loads(run.model_dump_json())
    assert data["claims"][0]["citation"] == "https://github.com/rustdev/fastdb"
    assert data["grounding_score"] == 1.0
    assert DemoRun.model_validate(data).candidate.login == "rustdev"
```

- [ ] **Step 3: Run it, expect failure**

Run: `/opt/sourcerer/.venv/bin/python -m pytest tests/test_demo_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sourcerer.demo.schema'`.

- [ ] **Step 4: Implement**

```python
# src/sourcerer/demo/schema.py
from pydantic import BaseModel
from sourcerer.models import Brief, Assessment, EvidenceBundle
from sourcerer.evals.scorers import grounding_score


class DemoClaim(BaseModel):
    text: str
    citation: str


class DemoEvidence(BaseModel):
    kind: str
    source_url: str
    text: str


class DemoSpan(BaseModel):
    name: str
    ms: float
    ok: bool


class DemoCandidate(BaseModel):
    login: str
    name: str | None = None
    profile_url: str


class DemoRun(BaseModel):
    role: str
    languages: list[str]
    candidate: DemoCandidate
    fit_score: float
    grounding_score: float
    claims: list[DemoClaim]
    unverified: list[str]
    outreach_draft: str
    evidence: list[DemoEvidence]
    spans: list[DemoSpan]
    model: str
    generated_at: str


def to_demo_run(brief: Brief, assessment: Assessment, bundle: EvidenceBundle,
                spans: list[dict], model: str, generated_at: str) -> DemoRun:
    return DemoRun(
        role=brief.role,
        languages=list(brief.languages),
        candidate=DemoCandidate(
            login=assessment.candidate.login,
            name=assessment.candidate.name,
            profile_url=assessment.candidate.profile_url,
        ),
        fit_score=assessment.fit_score,
        grounding_score=grounding_score(assessment, bundle),
        claims=[DemoClaim(text=c.text, citation=c.citation) for c in assessment.claims],
        unverified=list(assessment.unverified),
        outreach_draft=assessment.outreach_draft,
        evidence=[DemoEvidence(kind=e.kind, source_url=e.source_url, text=e.text)
                  for e in bundle.items],
        spans=[DemoSpan(name=s["name"], ms=s["ms"], ok=s["ok"]) for s in spans],
        model=model,
        generated_at=generated_at,
    )
```

- [ ] **Step 5: Run + full suite + commit**

Run: `/opt/sourcerer/.venv/bin/python -m pytest tests/test_demo_schema.py -v` → PASS, then `/opt/sourcerer/.venv/bin/python -m pytest -q` → all green.
```bash
git add src/sourcerer/demo/__init__.py src/sourcerer/demo/schema.py tests/test_demo_schema.py
git commit -m "feat(demo): DemoRun schema + to_demo_run serializer"
```

---

### Task 2: Offline generator (presets, mock-tested core + live entrypoint)

**Files:**
- Create: `src/sourcerer/demo/generate.py`
- Test: `tests/test_demo_generate.py`

**Interfaces:**
- Consumes: `sourcerer.config.get_settings`, `sourcerer.models.Brief`, `sourcerer.github` (`HttpGitHub`, `GitHubClient`), `sourcerer.web` (`HttpFetcher`, `Fetcher`), `sourcerer.llm` (`LiteLLMClient`, `LLMClient`), `sourcerer.pipeline.run`, `sourcerer.trace` (`reset_spans`, `get_spans`), `sourcerer.demo.schema` (`DemoRun`, `to_demo_run`).
- Produces: `PRESETS: list[dict]`, `preset_to_brief(preset) -> Brief`, `build_manifest(presets) -> dict`, `async generate_one(preset, gh, fetcher, llm, model, generated_at) -> DemoRun`, `write_demo(out_dir: Path, runs: dict[str, DemoRun], manifest: dict) -> None`, `async main() -> None`.

- [ ] **Step 1: Write the failing test (all network-free)**

```python
# tests/test_demo_generate.py
import json
from sourcerer.github import MockGitHub
from sourcerer.web import MockFetcher, PageContent
from sourcerer.llm import MockLLM
from sourcerer.demo.schema import DemoRun, DemoCandidate
from sourcerer.demo.generate import (
    PRESETS, preset_to_brief, build_manifest, generate_one, write_demo,
)


def test_preset_to_brief_maps_role_and_languages():
    b = preset_to_brief({"slug": "x", "label": "X", "role": "Rust eng", "languages": ["rust"]})
    assert b.role == "Rust eng" and b.languages == ["rust"] and b.max_candidates == 1


def test_build_manifest_lists_all_presets():
    m = build_manifest(PRESETS)
    assert len(m["presets"]) == len(PRESETS)
    assert {"slug", "label", "role", "languages"} <= set(m["presets"][0].keys())


async def test_generate_one_with_mocks_produces_grounded_demo_run():
    preset = {"slug": "rust", "label": "Rust", "role": "Rust systems engineer", "languages": ["rust"]}
    gh = MockGitHub(
        users=[{"login": "rustdev", "name": "Rusty", "html_url": "https://github.com/rustdev",
                "blog": "https://rusty.dev", "followers": 300, "bio": "systems"}],
        repos={"rustdev": [{"name": "fastdb", "language": "Rust", "stargazers_count": 900,
                            "html_url": "https://github.com/rustdev/fastdb", "description": "embedded db"}]})
    fetcher = MockFetcher({"https://rusty.dev": PageContent(
        url="https://rusty.dev", title="Rusty", text="I build embedded Rust databases")})
    payload = json.dumps({"fit_score": 0.92,
        "claims": [{"text": "Authored fastdb", "citation": "https://github.com/rustdev/fastdb"}],
        "unverified": [], "outreach_draft": "Hi Rusty"})
    run = await generate_one(preset, gh, fetcher, MockLLM(lambda s, u: payload),
                             model="m", generated_at="t")
    assert isinstance(run, DemoRun)
    assert run.candidate.login == "rustdev"
    assert run.grounding_score == 1.0
    assert {s.name for s in run.spans} >= {"discover", "research", "synthesize"}


def test_write_demo_writes_manifest_and_per_slug(tmp_path):
    run = DemoRun(role="r", languages=["rust"],
                  candidate=DemoCandidate(login="x", name=None, profile_url="https://github.com/x"),
                  fit_score=0.5, grounding_score=1.0, claims=[], unverified=[],
                  outreach_draft="hi", evidence=[], spans=[], model="m", generated_at="t")
    write_demo(tmp_path, {"rust": run},
               {"presets": [{"slug": "rust", "label": "Rust", "role": "r", "languages": ["rust"]}]})
    assert (tmp_path / "manifest.json").exists()
    assert json.loads((tmp_path / "rust.json").read_text())["candidate"]["login"] == "x"
    assert json.loads((tmp_path / "manifest.json").read_text())["presets"][0]["slug"] == "rust"
```

- [ ] **Step 2: Run it, expect failure**

Run: `/opt/sourcerer/.venv/bin/python -m pytest tests/test_demo_generate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sourcerer.demo.generate'`.

- [ ] **Step 3: Implement**

```python
# src/sourcerer/demo/generate.py
import asyncio
import json
from pathlib import Path

from sourcerer.config import get_settings
from sourcerer.models import Brief
from sourcerer.github import HttpGitHub, GitHubClient
from sourcerer.web import HttpFetcher, Fetcher
from sourcerer.llm import LiteLLMClient, LLMClient
from sourcerer.pipeline import run
from sourcerer.trace import reset_spans, get_spans
from sourcerer.demo.schema import DemoRun, to_demo_run

PRESETS: list[dict] = [
    {"slug": "rust-systems-engineer", "label": "Rust systems engineer",
     "role": "Rust systems engineer", "languages": ["rust"]},
    {"slug": "react-typescript-frontend", "label": "React / TypeScript frontend",
     "role": "React TypeScript frontend engineer", "languages": ["typescript"]},
    {"slug": "ml-infra-pytorch", "label": "ML infra (PyTorch)",
     "role": "Machine learning infrastructure engineer", "languages": ["python"]},
    {"slug": "go-distributed-systems", "label": "Go distributed systems",
     "role": "Go distributed systems engineer", "languages": ["go"]},
]


def preset_to_brief(preset: dict) -> Brief:
    return Brief(role=preset["role"], languages=list(preset["languages"]), max_candidates=1)


def build_manifest(presets: list[dict]) -> dict:
    return {"presets": [
        {"slug": p["slug"], "label": p["label"], "role": p["role"], "languages": list(p["languages"])}
        for p in presets
    ]}


async def generate_one(preset: dict, gh: GitHubClient, fetcher: Fetcher, llm: LLMClient,
                       model: str, generated_at: str) -> DemoRun:
    brief = preset_to_brief(preset)
    reset_spans()
    results = await run(brief, gh, fetcher, llm, model)
    assessment, bundle = results[0]
    return to_demo_run(brief, assessment, bundle, get_spans(), model, generated_at)


def write_demo(out_dir: Path, runs: dict[str, DemoRun], manifest: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for slug, demo_run in runs.items():
        (out_dir / f"{slug}.json").write_text(demo_run.model_dump_json(indent=2))


async def main() -> None:
    import datetime
    settings = get_settings()
    gh, fetcher, llm = HttpGitHub(settings.github_token), HttpFetcher(), LiteLLMClient()
    generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    runs: dict[str, DemoRun] = {}
    for preset in PRESETS:
        runs[preset["slug"]] = await generate_one(preset, gh, fetcher, llm, settings.model, generated_at)
        print(f"generated {preset['slug']}")
    out_dir = Path(__file__).resolve().parents[3] / "web" / "demo"
    write_demo(out_dir, runs, build_manifest(PRESETS))
    print(f"wrote {len(runs)} demo runs + manifest to {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run + full suite + commit**

Run: `/opt/sourcerer/.venv/bin/python -m pytest tests/test_demo_generate.py -v` → PASS, then `/opt/sourcerer/.venv/bin/python -m pytest -q` → all green.
```bash
git add src/sourcerer/demo/generate.py tests/test_demo_generate.py
git commit -m "feat(demo): offline generator (presets, generate_one, write_demo, main)"
```

---

### Task 3: Static demo page (HTML/CSS/JS)

**Files:**
- Create: `web/index.html`, `web/sourcerer.css`, `web/sourcerer.js`

**Interfaces:**
- Consumes (at runtime, in the browser): `demo/manifest.json` (`{presets:[{slug,label,role,languages}]}`) and `demo/<slug>.json` (a serialized `DemoRun`).
- Produces: the static page. No Python interface.

Not TDD (static front-end). Verified by serving locally and loading it.

- [ ] **Step 1: Write `web/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sourcerer — grounded technical sourcing</title>
  <link rel="stylesheet" href="sourcerer.css" />
</head>
<body>
  <main>
    <header>
      <h1>Sourcerer</h1>
      <p class="tagline">An AI technical-sourcing agent. It finds an engineer, researches them
        from public sources, and writes a <strong>grounded, cited</strong> fit-brief — every claim
        must point at real evidence, or it doesn't get made.</p>
    </header>
    <section class="how">
      <p>Pick a role. Watch it run <code>discover &rarr; research &rarr; synthesize</code>, then read
        the brief — with the <strong>grounding score</strong>, clickable citations, and the
        <strong>&ldquo;unverified&rdquo; list</strong> of things it refused to assert.
        <a href="https://github.com/Dr-Inker/sourcerer" target="_blank" rel="noopener">Source on GitHub &#8599;</a></p>
    </section>
    <nav id="presets" class="presets"></nav>
    <section id="stages" class="stages"></section>
    <section id="result" class="result"></section>
  </main>
  <script src="sourcerer.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `web/sourcerer.css`**

```css
:root{--bg:#0e0f13;--panel:#16181f;--ink:#e8e8ea;--muted:#9aa0aa;--accent:#36e2b4;--accent2:#7aa2ff;--line:#262a34}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:40px 20px 80px}
h1{font-size:2.2rem;margin:0 0 .2em;letter-spacing:-.02em}
.tagline{font-size:1.05rem}
.how{color:var(--muted);font-size:.95rem;border-left:2px solid var(--line);padding-left:14px;margin:24px 0}
.how code{color:var(--accent)}
a{color:var(--accent2);text-decoration:none}a:hover{text-decoration:underline}
.presets{display:flex;flex-wrap:wrap;gap:10px;margin:24px 0}
.preset{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:10px 14px;cursor:pointer;font:inherit}
.preset:hover{border-color:var(--accent)}
.stages{margin:18px 0;display:flex;flex-direction:column;gap:8px}
.stage{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px 12px;color:var(--muted)}
.stage.done{color:var(--ink)}.stage.done.err{color:#ff8080}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;vertical-align:-1px;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
.cand h3{margin:.2em 0}
.scores{display:flex;gap:12px;margin:6px 0 18px}
.score{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:4px 10px;color:var(--muted)}
.score b{color:var(--ink)}.score.grounded b{color:var(--accent)}
h4{margin:22px 0 8px}
.muted{color:var(--muted)}
ul{margin:.2em 0;padding-left:1.2em}
.claims li{margin:.3em 0}
.cite{font-size:.85rem}
.unverified li{color:var(--muted)}
.outreach{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px;white-space:pre-wrap}
.sources{margin:18px 0;color:var(--muted)}
.sources .kind{color:var(--accent);font-size:.8rem;margin-right:6px}
.stamp{margin-top:24px;font-size:.85rem}
```

- [ ] **Step 3: Write `web/sourcerer.js`**

```javascript
const REPO_URL = "https://github.com/Dr-Inker/sourcerer";
const DEMO_BASE = "demo";
const STAGE_ORDER = ["discover", "research", "synthesize"];
const STAGE_LABEL = { discover: "Discover", research: "Research", synthesize: "Synthesize" };

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function loadManifest() {
  try {
    const r = await fetch(`${DEMO_BASE}/manifest.json`, { cache: "no-store" });
    if (!r.ok) throw new Error();
    return (await r.json()).presets || [];
  } catch {
    return [];
  }
}

function renderPresets(presets) {
  const nav = document.getElementById("presets");
  nav.innerHTML = "";
  if (!presets.length) {
    nav.innerHTML = '<p class="muted">No sample runs generated yet.</p>';
    return;
  }
  presets.forEach((p) => {
    const b = document.createElement("button");
    b.className = "preset";
    b.textContent = p.label;
    b.onclick = () => runPreset(p);
    nav.appendChild(b);
  });
}

async function runPreset(preset) {
  const out = document.getElementById("result");
  const stageBox = document.getElementById("stages");
  out.innerHTML = "";
  stageBox.innerHTML = "";
  let data;
  try {
    const r = await fetch(`${DEMO_BASE}/${preset.slug}.json`, { cache: "no-store" });
    if (!r.ok) throw new Error();
    data = await r.json();
  } catch {
    stageBox.innerHTML = `<p class="muted">Sample run for "${esc(preset.label)}" hasn't been generated yet.</p>`;
    return;
  }
  await playStages(stageBox, data.spans || []);
  renderResult(out, data);
}

async function playStages(box, spans) {
  const byName = Object.fromEntries(spans.map((s) => [s.name, s]));
  for (const name of STAGE_ORDER) {
    const row = document.createElement("div");
    row.className = "stage running";
    row.innerHTML = `<span class="spin"></span> ${STAGE_LABEL[name] || name}&hellip;`;
    box.appendChild(row);
    const rec = byName[name];
    const ms = rec ? Math.min(1200, Math.max(300, rec.ms * 8)) : 500;
    await sleep(ms);
    const ok = rec ? rec.ok : true;
    row.className = "stage done" + (ok ? "" : " err");
    row.innerHTML = `${ok ? "✓" : "✗"} ${STAGE_LABEL[name] || name}`;
  }
}

function renderResult(out, d) {
  const c = d.candidate || {};
  const claims = (d.claims || [])
    .map((cl) => `<li>${esc(cl.text)} <a class="cite" href="${esc(cl.citation)}" target="_blank" rel="noopener">source &#8599;</a></li>`)
    .join("");
  const unverified = (d.unverified || []).map((u) => `<li>${esc(u)}</li>`).join("");
  const sources = (d.evidence || [])
    .map((e) => `<li><span class="kind">${esc(e.kind)}</span> <a href="${esc(e.source_url)}" target="_blank" rel="noopener">${esc(e.source_url)}</a></li>`)
    .join("");
  out.innerHTML = `
    <div class="cand">
      <h3>${esc(c.name || c.login)} <a href="${esc(c.profile_url)}" target="_blank" rel="noopener">@${esc(c.login)} &#8599;</a></h3>
      <div class="scores">
        <span class="score">fit <b>${(d.fit_score ?? 0).toFixed(2)}</b></span>
        <span class="score grounded">grounding <b>${(d.grounding_score ?? 0).toFixed(2)}</b></span>
      </div>
    </div>
    <h4>Grounded claims <span class="muted">(each cites real evidence)</span></h4>
    <ul class="claims">${claims || '<li class="muted">none</li>'}</ul>
    ${unverified ? `<h4>Unverified <span class="muted">&mdash; stated, but the agent refused to assert it</span></h4><ul class="unverified">${unverified}</ul>` : ""}
    <h4>Outreach draft</h4>
    <pre class="outreach">${esc(d.outreach_draft)}</pre>
    <details class="sources"><summary>Evidence (${(d.evidence || []).length})</summary><ul>${sources}</ul></details>
    <p class="stamp muted">Cached sample run &middot; model ${esc(d.model)} &middot; generated ${esc(d.generated_at)} &middot; <a href="${REPO_URL}" target="_blank" rel="noopener">run it yourself &#8599;</a></p>
  `;
}

(async function () {
  renderPresets(await loadManifest());
})();
```

- [ ] **Step 4: Create a verification fixture and serve locally**

Create a hand-made sample so the page can be verified without keys (these files are git-ignored and will be overwritten by the real generator):

```bash
mkdir -p /opt/sourcerer/web/demo
cat > /opt/sourcerer/web/demo/manifest.json <<'JSON'
{"presets":[{"slug":"rust-systems-engineer","label":"Rust systems engineer","role":"Rust systems engineer","languages":["rust"]}]}
JSON
cat > /opt/sourcerer/web/demo/rust-systems-engineer.json <<'JSON'
{"role":"Rust systems engineer","languages":["rust"],
 "candidate":{"login":"rustdev","name":"Rusty","profile_url":"https://github.com/rustdev"},
 "fit_score":0.92,"grounding_score":1.0,
 "claims":[{"text":"Authored fastdb, an embedded Rust DB","citation":"https://github.com/rustdev/fastdb"}],
 "unverified":["Worked at BigCo"],"outreach_draft":"Hi Rusty — loved fastdb...",
 "evidence":[{"kind":"github_repo","source_url":"https://github.com/rustdev/fastdb","text":"fastdb (Rust, ★900): embedded db"}],
 "spans":[{"name":"discover","ms":12,"ok":true},{"name":"research","ms":30,"ok":true},{"name":"synthesize","ms":50,"ok":true}],
 "model":"openrouter/z-ai/glm-5.1","generated_at":"2026-06-27T12:00:00Z"}
JSON
cd /opt/sourcerer/web && /opt/sourcerer/.venv/bin/python -m http.server 8099 &
sleep 1
curl -s -o /dev/null -w "index:%{http_code} js:" http://127.0.0.1:8099/index.html
curl -s -o /dev/null -w "%{http_code} json:" http://127.0.0.1:8099/sourcerer.js
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8099/demo/rust-systems-engineer.json
```
Expected: `index:200 js:200 json:200`.

- [ ] **Step 5: Visually verify the render (Playwright MCP if available, else manual)**

Load `http://127.0.0.1:8099/` in a browser (or the Playwright MCP), click the "Rust systems engineer" preset, and confirm: the three stages animate then check off; the candidate header, fit/grounding scores, the grounded claim with a clickable "source" link, the "Unverified" list, and the outreach draft all render; the timestamp/repo line shows. Then stop the server: `kill %1` (or `pkill -f "http.server 8099"`).

- [ ] **Step 6: Commit (page assets only; the demo/ fixture is git-ignored)**

```bash
git add web/index.html web/sourcerer.css web/sourcerer.js
git commit -m "feat(demo): static replay page (grounding-forward, dependency-free)"
```

---

### Task 4: Deploy script, gitignore, README

**Files:**
- Create: `deploy/deploy-demo.sh`, `web/README.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `python -m sourcerer.demo.generate`, the `web/` static assets.
- Produces: a publish step to `/var/www/drinkerlabs/sourcerer/`.

- [ ] **Step 1: Git-ignore the generated artifacts**

Append to `/opt/sourcerer/.gitignore`:
```
# Generated demo artifacts (produced by sourcerer.demo.generate)
web/demo/
```

- [ ] **Step 2: Write `web/README.md`**

```markdown
# Sourcerer demo (static)

The public demo at `drinkerlabs.info/sourcerer/`. Pure static — no backend, no
secrets on the public path. It **replays** real pipeline runs that were
generated offline.

## Files
- `index.html` / `sourcerer.css` / `sourcerer.js` — the page (committed).
- `demo/*.json` — generated cached runs + `manifest.json` (git-ignored).

## Regenerate the cached runs (needs keys)
Requires `OPENROUTER_API_KEY` + `GITHUB_TOKEN` in `/opt/sourcerer/.env`
(the generator makes real GitHub + LLM calls):

    /opt/sourcerer/.venv/bin/python -m sourcerer.demo.generate

## Publish to the live site
    bash /opt/sourcerer/deploy/deploy-demo.sh
```

- [ ] **Step 3: Write `deploy/deploy-demo.sh`**

```bash
#!/usr/bin/env bash
# Generate the cached demo runs, then publish the static demo to the live webroot.
# Requires OPENROUTER_API_KEY + GITHUB_TOKEN in /opt/sourcerer/.env (the generator
# makes real calls). Idempotent: overwrites web/demo/*.json and the webroot copy.
set -euo pipefail
cd /opt/sourcerer
WEBROOT=/var/www/drinkerlabs/sourcerer

echo "1/3 generating cached demo runs (real GitHub + LLM)..."
.venv/bin/python -m sourcerer.demo.generate

echo "2/3 publishing static assets to ${WEBROOT}..."
mkdir -p "${WEBROOT}/demo"
cp web/index.html web/sourcerer.css web/sourcerer.js "${WEBROOT}/"
cp web/demo/*.json "${WEBROOT}/demo/"

echo "3/3 done. Verify:"
echo "  curl -sI https://drinkerlabs.info/sourcerer/ | head -1"
echo "  curl -sI https://drinkerlabs.info/sourcerer/demo/manifest.json | head -1"
```

- [ ] **Step 4: Make it executable, verify the suite, commit**

```bash
chmod +x /opt/sourcerer/deploy/deploy-demo.sh
/opt/sourcerer/.venv/bin/python -m pytest -q   # all green
git add .gitignore web/README.md deploy/deploy-demo.sh
git commit -m "chore(demo): deploy script, README, gitignore generated artifacts"
```

- [ ] **Step 5: Pre-deploy nginx check (read-only; no go-live yet)**

Confirm the existing catch-all serves a new subdir + `.json` (expected: no nginx change needed). Inspect the drinkerlabs server block's `location /` and `root`:
```bash
grep -nE "root |location / |try_files|index " /etc/nginx/sites-available/drinkerlabs | head
```
If `root /var/www/drinkerlabs;` and the catch-all serves static files (it serves `/game/`, `/bert/`), then `/sourcerer/` will serve once files are copied. If a dedicated block is needed (e.g. to force `Content-Type: application/json` or `autoindex`), note it here for the human — do not edit nginx without sign-off.

- [ ] **Step 6: Go-live (HUMAN-GATED — run only with approval and keys present)**

This is the only outward-facing step and needs `OPENROUTER_API_KEY` + `GITHUB_TOKEN` in `.env`. With approval:
```bash
bash /opt/sourcerer/deploy/deploy-demo.sh
curl -sI https://drinkerlabs.info/sourcerer/ | head -1            # expect HTTP/2 200
curl -sI https://drinkerlabs.info/sourcerer/demo/manifest.json | head -1  # expect 200
```
If keys are absent, skip the generate step's real run — ship the page only (the graceful placeholder shows) and re-run this step once keys are available. Never hand-edit JSON to fake a run.

---

## Phase-2 Increment 1 Done =
`pytest` all green (existing 21 + the new schema/generator tests, all network-free); `web/` page renders a preset's staged replay + grounded brief from a `DemoRun` JSON; `deploy-demo.sh` generates real cached runs and publishes to `/var/www/drinkerlabs/sourcerer/`; and (human-gated) `drinkerlabs.info/sourcerer/` serves the live demo. **Deferred to later increments:** live re-run button, free-text input, HITL approve-and-send, and the rest of the Phase-2 backlog.
