# Sourcerer — Phase 1 (Vertical Slice) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CLI that takes a sourcing brief, discovers one GitHub candidate, researches them (GitHub API + one deterministic web source), and produces a *grounded, cited* fit-brief + personalized outreach draft — with eval scorers and tracing proving it works.

**Architecture:** Plain async pipeline with clean, mockable interfaces (`discover → research → synthesize`). Every external dependency (GitHub, web fetch, LLM) sits behind a Protocol with a deterministic mock, so the whole pipeline is unit-tested with no network. LangGraph orchestration, parallel fan-out, the HITL UI, the agentic browser, and the reply-loop are deliberately deferred to later phases — this phase establishes the spine and the grounding/eval discipline.

**Tech Stack:** Python 3.12 · pydantic v2 · httpx · pytest + pytest-asyncio · selectolax (HTML→text) · LiteLLM (real LLM calls; mocked in tests). Spec: `docs/superpowers/specs/2026-06-27-sourcerer-design.md`.

## Global Constraints
- Python ≥ 3.12; all I/O async (`async def`, `httpx.AsyncClient`).
- Public sources only; GitHub via its REST API within rate limits; web fetch respects `robots.txt` + a timeout. No LinkedIn, no ToS-violating scraping. (Enforced from Task 6 onward.)
- Every dependency that does I/O is a `typing.Protocol` with a deterministic mock; no test makes a network call.
- Grounding rule (load-bearing): a claim in an `Assessment` may only assert a fact whose `citation` URL appears in the candidate's gathered evidence; ungrounded statements go in `unverified`, never `claims`.
- Secrets from env via `python-dotenv`; never hardcoded. Package name `sourcerer`. TDD: test first, frequent commits.

## File Structure
- `pyproject.toml` — package + deps + pytest config
- `.env.example` — `OPENROUTER_API_KEY`, `GITHUB_TOKEN`, `SOURCERER_MODEL`
- `src/sourcerer/__init__.py`
- `src/sourcerer/config.py` — env-backed settings
- `src/sourcerer/models.py` — pydantic domain models (the shared vocabulary)
- `src/sourcerer/llm.py` — `LLMClient` protocol, `MockLLM`, `LiteLLMClient`
- `src/sourcerer/github.py` — `GitHubClient` protocol, `MockGitHub`, `HttpGitHub`
- `src/sourcerer/web.py` — `Fetcher` protocol, `MockFetcher`, `HttpFetcher`
- `src/sourcerer/discovery.py` — `discover(brief, gh)`
- `src/sourcerer/research.py` — `research(candidate, gh, fetcher)`
- `src/sourcerer/synthesis.py` — `synthesize(candidate, bundle, llm)`
- `src/sourcerer/trace.py` — `traced()` span recorder
- `src/sourcerer/evals/scorers.py` — `grounding_score`, `claims_resolve`
- `src/sourcerer/pipeline.py` — `run(brief, gh, fetcher, llm)`
- `src/sourcerer/cli.py` — entry point
- `tests/…` — one test module per source module
- `evals/golden.json` — tiny labeled golden set

---

### Task 1: Scaffold + config

**Files:**
- Create: `pyproject.toml`, `.env.example`, `src/sourcerer/__init__.py`, `src/sourcerer/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `config.Settings` with `.github_token: str|None`, `.openrouter_api_key: str|None`, `.model: str` (default `"anthropic/claude-sonnet-4.6"`); `config.get_settings() -> Settings`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "sourcerer"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.7", "httpx>=0.27", "selectolax>=0.3", "litellm>=1.50", "python-dotenv>=1.0"]
[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]
[project.scripts]
sourcerer = "sourcerer.cli:main"
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_config.py
from sourcerer.config import get_settings
def test_defaults_to_known_model(monkeypatch):
    monkeypatch.delenv("SOURCERER_MODEL", raising=False)
    assert get_settings().model == "anthropic/claude-sonnet-4.6"
def test_reads_model_from_env(monkeypatch):
    monkeypatch.setenv("SOURCERER_MODEL", "gemini-2.5-flash")
    assert get_settings().model == "gemini-2.5-flash"
```

- [ ] **Step 3: Run it, expect failure**

Run: `pip install -e ".[dev]" && pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: sourcerer.config`)

- [ ] **Step 4: Implement**

```python
# src/sourcerer/config.py
import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

@dataclass(frozen=True)
class Settings:
    github_token: str | None
    openrouter_api_key: str | None
    model: str

def get_settings() -> Settings:
    return Settings(
        github_token=os.getenv("GITHUB_TOKEN"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        model=os.getenv("SOURCERER_MODEL", "anthropic/claude-sonnet-4.6"),
    )
```
Also create empty `src/sourcerer/__init__.py` and `.env.example` with the three keys.

- [ ] **Step 5: Run + commit**

Run: `pytest tests/test_config.py -v` → PASS
```bash
git add pyproject.toml .env.example src/sourcerer/__init__.py src/sourcerer/config.py tests/test_config.py
git commit -m "chore: scaffold sourcerer package + config"
```

---

### Task 2: Domain models (the shared vocabulary)

**Files:**
- Create: `src/sourcerer/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces (used by every later task):
  - `Brief(role:str, languages:list[str]=[], topics:list[str]=[], must_have:list[str]=[], voice:str="warm, specific, concise", max_candidates:int=1)`
  - `Candidate(login:str, name:str|None, profile_url:str, signals:dict=, sources:list[str]=)`
  - `Evidence(source_url:str, kind:str, text:str)` — `kind ∈ {"github_profile","github_repo","web_page"}`
  - `EvidenceBundle(candidate:Candidate, items:list[Evidence])` with `.source_urls() -> set[str]`
  - `Claim(text:str, citation:str)`
  - `Assessment(candidate:Candidate, fit_score:float, claims:list[Claim], unverified:list[str], outreach_draft:str)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from sourcerer.models import Brief, Candidate, Evidence, EvidenceBundle, Claim, Assessment
def test_bundle_exposes_source_urls():
    c = Candidate(login="octocat", name="Octo", profile_url="https://github.com/octocat")
    b = EvidenceBundle(candidate=c, items=[
        Evidence(source_url="https://github.com/octocat", kind="github_profile", text="bio"),
        Evidence(source_url="https://octo.dev", kind="web_page", text="blog"),
    ])
    assert b.source_urls() == {"https://github.com/octocat", "https://octo.dev"}
def test_assessment_defaults():
    c = Candidate(login="x", name=None, profile_url="https://github.com/x")
    a = Assessment(candidate=c, fit_score=0.8, claims=[Claim(text="ships Rust", citation="https://github.com/x")], unverified=[], outreach_draft="hi")
    assert a.fit_score == 0.8 and a.claims[0].citation == "https://github.com/x"
```

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/test_models.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# src/sourcerer/models.py
from pydantic import BaseModel, Field

class Brief(BaseModel):
    role: str
    languages: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    voice: str = "warm, specific, concise"
    max_candidates: int = 1

class Candidate(BaseModel):
    login: str
    name: str | None = None
    profile_url: str
    signals: dict = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)

class Evidence(BaseModel):
    source_url: str
    kind: str
    text: str

class EvidenceBundle(BaseModel):
    candidate: Candidate
    items: list[Evidence] = Field(default_factory=list)
    def source_urls(self) -> set[str]:
        return {e.source_url for e in self.items}

class Claim(BaseModel):
    text: str
    citation: str

class Assessment(BaseModel):
    candidate: Candidate
    fit_score: float
    claims: list[Claim] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    outreach_draft: str
```

- [ ] **Step 4: Run + commit** — PASS, then:
```bash
git add src/sourcerer/models.py tests/test_models.py
git commit -m "feat: domain models"
```

---

### Task 3: LLM client (protocol + mock + real)

**Files:**
- Create: `src/sourcerer/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Produces: `LLMClient` protocol with `async def complete(self, system:str, user:str, model:str) -> str`; `MockLLM(responder: Callable[[str,str], str])` recording `.calls`; `LiteLLMClient` (real, via litellm).

- [ ] **Step 1: Failing test**

```python
# tests/test_llm.py
import pytest
from sourcerer.llm import MockLLM
async def test_mock_records_calls_and_returns():
    m = MockLLM(lambda system, user: '{"ok": true}')
    out = await m.complete(system="s", user="u", model="x")
    assert out == '{"ok": true}'
    assert m.calls[0] == {"system": "s", "user": "u", "model": "x"}
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**

```python
# src/sourcerer/llm.py
from typing import Protocol, Callable

class LLMClient(Protocol):
    async def complete(self, system: str, user: str, model: str) -> str: ...

class MockLLM:
    def __init__(self, responder: Callable[[str, str], str]):
        self._responder = responder
        self.calls: list[dict] = []
    async def complete(self, system: str, user: str, model: str) -> str:
        self.calls.append({"system": system, "user": user, "model": model})
        return self._responder(system, user)

class LiteLLMClient:
    async def complete(self, system: str, user: str, model: str) -> str:
        import litellm
        resp = await litellm.acompletion(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.3, response_format={"type": "json_object"},
        )
        return resp["choices"][0]["message"]["content"]
```

- [ ] **Step 4: Run + commit**
```bash
git add src/sourcerer/llm.py tests/test_llm.py
git commit -m "feat: LLM client protocol + mock + litellm impl"
```

---

### Task 4: GitHub client (protocol + mock + real)

**Files:**
- Create: `src/sourcerer/github.py`
- Test: `tests/test_github.py`

**Interfaces:**
- Produces: `GitHubClient` protocol: `async def search_users(self, query:str, limit:int) -> list[dict]`, `async def get_user(self, login:str) -> dict`, `async def list_repos(self, login:str, limit:int) -> list[dict]`. `MockGitHub(users, repos)` returns canned data. `HttpGitHub(token)` (real, httpx).

- [ ] **Step 1: Failing test**

```python
# tests/test_github.py
from sourcerer.github import MockGitHub
async def test_mock_search_and_repos():
    gh = MockGitHub(
        users=[{"login": "rustdev", "name": "Rusty", "html_url": "https://github.com/rustdev", "blog": "https://rusty.dev", "bio": "systems"}],
        repos={"rustdev": [{"name": "fastdb", "language": "Rust", "stargazers_count": 900, "html_url": "https://github.com/rustdev/fastdb", "description": "embedded db"}]},
    )
    assert (await gh.search_users("language:rust", 5))[0]["login"] == "rustdev"
    assert (await gh.list_repos("rustdev", 5))[0]["language"] == "Rust"
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**

```python
# src/sourcerer/github.py
from typing import Protocol
import httpx

class GitHubClient(Protocol):
    async def search_users(self, query: str, limit: int) -> list[dict]: ...
    async def get_user(self, login: str) -> dict: ...
    async def list_repos(self, login: str, limit: int) -> list[dict]: ...

class MockGitHub:
    def __init__(self, users: list[dict], repos: dict[str, list[dict]]):
        self._users, self._repos = users, repos
    async def search_users(self, query: str, limit: int) -> list[dict]:
        return self._users[:limit]
    async def get_user(self, login: str) -> dict:
        return next(u for u in self._users if u["login"] == login)
    async def list_repos(self, login: str, limit: int) -> list[dict]:
        return self._repos.get(login, [])[:limit]

class HttpGitHub:
    def __init__(self, token: str | None):
        self._h = {"Authorization": f"Bearer {token}"} if token else {}
    async def search_users(self, query: str, limit: int) -> list[dict]:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get("https://api.github.com/search/users",
                            params={"q": query, "per_page": limit}, headers=self._h)
            r.raise_for_status()
            items = r.json().get("items", [])
            return [await self.get_user(i["login"]) for i in items]
    async def get_user(self, login: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"https://api.github.com/users/{login}", headers=self._h)
            r.raise_for_status(); return r.json()
    async def list_repos(self, login: str, limit: int) -> list[dict]:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"https://api.github.com/users/{login}/repos",
                            params={"sort": "pushed", "per_page": limit}, headers=self._h)
            r.raise_for_status(); return r.json()
```

- [ ] **Step 4: Run + commit**
```bash
git add src/sourcerer/github.py tests/test_github.py
git commit -m "feat: GitHub client protocol + mock + http impl"
```

---

### Task 5: Web fetcher (deterministic, robots-aware)

**Files:**
- Create: `src/sourcerer/web.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Produces: `PageContent(url:str, title:str, text:str)` (pydantic); `Fetcher` protocol `async def fetch(self, url:str) -> PageContent|None` (None if disallowed/failed); `MockFetcher(pages: dict[str, PageContent])`; `HttpFetcher` (httpx + selectolax text extraction + robots check + timeout).

- [ ] **Step 1: Failing test**

```python
# tests/test_web.py
from sourcerer.web import MockFetcher, PageContent, extract_text
async def test_mock_fetch_returns_known_page():
    p = PageContent(url="https://rusty.dev", title="Rusty", text="I love embedded Rust")
    f = MockFetcher({"https://rusty.dev": p})
    assert (await f.fetch("https://rusty.dev")).text == "I love embedded Rust"
    assert await f.fetch("https://missing.dev") is None
def test_extract_text_strips_markup():
    html = "<html><head><title>T</title></head><body><h1>Hi</h1><script>x</script><p>world</p></body></html>"
    title, text = extract_text(html)
    assert title == "T" and "Hi" in text and "world" in text and "x" not in text
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**

```python
# src/sourcerer/web.py
from typing import Protocol
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
import httpx
from selectolax.parser import HTMLParser
from pydantic import BaseModel

class PageContent(BaseModel):
    url: str; title: str; text: str

def extract_text(html: str) -> tuple[str, str]:
    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript"):
        tag.decompose()
    title = (tree.css_first("title").text() if tree.css_first("title") else "").strip()
    body = tree.body.text(separator=" ", strip=True) if tree.body else ""
    return title, " ".join(body.split())

class Fetcher(Protocol):
    async def fetch(self, url: str) -> PageContent | None: ...

class MockFetcher:
    def __init__(self, pages: dict[str, PageContent]):
        self._pages = pages
    async def fetch(self, url: str) -> PageContent | None:
        return self._pages.get(url)

class HttpFetcher:
    async def _allowed(self, url: str) -> bool:
        p = urlparse(url)
        rp = RobotFileParser(); rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(rp.url)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except httpx.HTTPError:
            return True  # no robots reachable → allowed
        return rp.can_fetch("sourcerer", url)
    async def fetch(self, url: str) -> PageContent | None:
        if not await self._allowed(url):
            return None
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
                r = await c.get(url, headers={"User-Agent": "sourcerer/0.1"})
                r.raise_for_status()
        except httpx.HTTPError:
            return None
        title, text = extract_text(r.text)
        return PageContent(url=url, title=title, text=text[:8000])
```

- [ ] **Step 4: Run + commit**
```bash
git add src/sourcerer/web.py tests/test_web.py
git commit -m "feat: robots-aware web fetcher + text extraction"
```

---

### Task 6: Discovery (brief → candidates)

**Files:**
- Create: `src/sourcerer/discovery.py`
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: `GitHubClient`, `Brief`, `Candidate`.
- Produces: `async def discover(brief: Brief, gh: GitHubClient) -> list[Candidate]` — builds a GitHub user-search query from the brief, returns up to `brief.max_candidates` candidates with `profile_url`, `name`, and `signals` (followers, blog).

- [ ] **Step 1: Failing test**

```python
# tests/test_discovery.py
from sourcerer.discovery import discover, build_query
from sourcerer.models import Brief
from sourcerer.github import MockGitHub
def test_build_query_includes_language_and_topics():
    q = build_query(Brief(role="x", languages=["rust"], topics=["databases"]))
    assert "language:rust" in q and "databases" in q
async def test_discover_maps_users_to_candidates():
    gh = MockGitHub(users=[{"login": "rustdev", "name": "Rusty", "html_url": "https://github.com/rustdev", "blog": "https://rusty.dev", "followers": 300}], repos={})
    cands = await discover(Brief(role="Rust eng", languages=["rust"], max_candidates=1), gh)
    assert cands[0].login == "rustdev" and cands[0].profile_url == "https://github.com/rustdev"
    assert cands[0].signals["blog"] == "https://rusty.dev"
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**

```python
# src/sourcerer/discovery.py
from sourcerer.models import Brief, Candidate
from sourcerer.github import GitHubClient

def build_query(brief: Brief) -> str:
    parts = [f"language:{lang}" for lang in brief.languages]
    parts += brief.topics
    parts.append("type:user")
    return " ".join(parts)

async def discover(brief: Brief, gh: GitHubClient) -> list[Candidate]:
    users = await gh.search_users(build_query(brief), brief.max_candidates)
    out: list[Candidate] = []
    for u in users:
        out.append(Candidate(
            login=u["login"], name=u.get("name"), profile_url=u["html_url"],
            signals={"followers": u.get("followers"), "blog": u.get("blog") or None, "bio": u.get("bio")},
            sources=[u["html_url"]],
        ))
    return out
```

- [ ] **Step 4: Run + commit**
```bash
git add src/sourcerer/discovery.py tests/test_discovery.py
git commit -m "feat: discovery (brief -> github candidates)"
```

---

### Task 7: Research (candidate → cited evidence)

**Files:**
- Create: `src/sourcerer/research.py`
- Test: `tests/test_research.py`

**Interfaces:**
- Consumes: `GitHubClient`, `Fetcher`, `Candidate`, `Evidence`, `EvidenceBundle`.
- Produces: `async def research(candidate: Candidate, gh: GitHubClient, fetcher: Fetcher) -> EvidenceBundle` — gathers (a) top repos as `github_repo` evidence, (b) the candidate's `blog` page (if present) as `web_page` evidence. Every `Evidence.source_url` is a real URL.

- [ ] **Step 1: Failing test**

```python
# tests/test_research.py
from sourcerer.research import research
from sourcerer.models import Candidate
from sourcerer.github import MockGitHub
from sourcerer.web import MockFetcher, PageContent
async def test_research_collects_repo_and_blog_evidence():
    cand = Candidate(login="rustdev", name="Rusty", profile_url="https://github.com/rustdev", signals={"blog": "https://rusty.dev"})
    gh = MockGitHub(users=[], repos={"rustdev": [{"name": "fastdb", "language": "Rust", "stargazers_count": 900, "html_url": "https://github.com/rustdev/fastdb", "description": "embedded db"}]})
    fetcher = MockFetcher({"https://rusty.dev": PageContent(url="https://rusty.dev", title="Rusty", text="I build embedded Rust databases")})
    bundle = await research(cand, gh, fetcher)
    urls = bundle.source_urls()
    assert "https://github.com/rustdev/fastdb" in urls
    assert "https://rusty.dev" in urls
    assert any(e.kind == "github_repo" for e in bundle.items)
    assert any(e.kind == "web_page" for e in bundle.items)
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**

```python
# src/sourcerer/research.py
from sourcerer.models import Candidate, Evidence, EvidenceBundle
from sourcerer.github import GitHubClient
from sourcerer.web import Fetcher

async def research(candidate: Candidate, gh: GitHubClient, fetcher: Fetcher) -> EvidenceBundle:
    items: list[Evidence] = []
    for repo in await gh.list_repos(candidate.login, limit=5):
        items.append(Evidence(
            source_url=repo["html_url"], kind="github_repo",
            text=f'{repo["name"]} ({repo.get("language")}, ★{repo.get("stargazers_count",0)}): {repo.get("description") or ""}',
        ))
    blog = candidate.signals.get("blog")
    if blog:
        page = await fetcher.fetch(blog)
        if page:
            items.append(Evidence(source_url=page.url, kind="web_page", text=f"{page.title}: {page.text}"))
    return EvidenceBundle(candidate=candidate, items=items)
```

- [ ] **Step 4: Run + commit**
```bash
git add src/sourcerer/research.py tests/test_research.py
git commit -m "feat: research (candidate -> cited evidence bundle)"
```

---

### Task 8: Synthesis (evidence → grounded brief + outreach), with the grounding guard

**Files:**
- Create: `src/sourcerer/synthesis.py`
- Test: `tests/test_synthesis.py`

**Interfaces:**
- Consumes: `LLMClient`, `EvidenceBundle`, `Candidate`, `Claim`, `Assessment`.
- Produces: `async def synthesize(candidate, bundle, llm, model) -> Assessment`. The LLM is asked for JSON `{"fit_score":0..1,"claims":[{"text","citation"}],"unverified":[...],"outreach_draft":"..."}`. **Grounding guard:** any claim whose `citation` is not in `bundle.source_urls()` is dropped from `claims` and its text appended to `unverified`. Also `extract_json(raw)` (tolerant parser) and clamped `fit_score`.

- [ ] **Step 1: Failing test**

```python
# tests/test_synthesis.py
import json
from sourcerer.synthesis import synthesize, extract_json
from sourcerer.models import Candidate, Evidence, EvidenceBundle
from sourcerer.llm import MockLLM
def test_extract_json_tolerates_fences_and_prose():
    assert extract_json('ok ```json\n{"a":1}\n``` done') == {"a": 1}
async def test_ungrounded_claim_is_moved_to_unverified():
    cand = Candidate(login="rustdev", name="Rusty", profile_url="https://github.com/rustdev")
    bundle = EvidenceBundle(candidate=cand, items=[Evidence(source_url="https://github.com/rustdev/fastdb", kind="github_repo", text="embedded db")])
    payload = json.dumps({"fit_score": 0.9,
        "claims": [{"text": "Built fastdb", "citation": "https://github.com/rustdev/fastdb"},
                   {"text": "Worked at BigCo", "citation": "https://linkedin.com/in/x"}],
        "unverified": [], "outreach_draft": "Hi Rusty"})
    a = await synthesize(cand, bundle, MockLLM(lambda s, u: payload), model="m")
    assert [c.text for c in a.claims] == ["Built fastdb"]
    assert "Worked at BigCo" in a.unverified
    assert a.fit_score == 0.9
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**

```python
# src/sourcerer/synthesis.py
import json
from sourcerer.models import Candidate, EvidenceBundle, Claim, Assessment
from sourcerer.llm import LLMClient

def extract_json(raw: str) -> dict:
    s = raw.replace("```json", "").replace("```", "").strip()
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1 or b < a:
        raise ValueError("no JSON object in response")
    return json.loads(s[a:b + 1])

def _system(voice: str) -> str:
    return (
        "You assess a software engineer for a sourcing brief, using ONLY the supplied evidence. "
        "For every factual claim you make, cite the exact evidence source_url it comes from. "
        "If you cannot ground a statement in the evidence, put it in 'unverified' — never assert it as a claim. "
        f"Write the outreach in this voice: {voice}. "
        'Respond ONLY with JSON: {"fit_score":<0..1>,"claims":[{"text":"","citation":"<source_url>"}],"unverified":[],"outreach_draft":""}'
    )

async def synthesize(candidate: Candidate, bundle: EvidenceBundle, llm: LLMClient, model: str, voice: str = "warm, specific, concise") -> Assessment:
    ev = "\n".join(f"- [{e.kind}] {e.source_url} :: {e.text}" for e in bundle.items)
    user = f"Candidate: {candidate.name or candidate.login} ({candidate.profile_url})\nEvidence:\n{ev}"
    data = extract_json(await llm.complete(_system(voice), user, model))
    valid_urls = bundle.source_urls()
    claims, unverified = [], list(data.get("unverified", []))
    for c in data.get("claims", []):
        if c.get("citation") in valid_urls:
            claims.append(Claim(text=c["text"], citation=c["citation"]))
        else:
            unverified.append(c.get("text", ""))
    score = max(0.0, min(1.0, float(data.get("fit_score", 0.0))))
    return Assessment(candidate=candidate, fit_score=score, claims=claims,
                      unverified=[u for u in unverified if u], outreach_draft=str(data.get("outreach_draft", "")).strip())
```

- [ ] **Step 4: Run + commit**
```bash
git add src/sourcerer/synthesis.py tests/test_synthesis.py
git commit -m "feat: grounded synthesis (brief + outreach) with citation guard"
```

---

### Task 9: Eval scorers + golden set

**Files:**
- Create: `src/sourcerer/evals/__init__.py`, `src/sourcerer/evals/scorers.py`, `evals/golden.json`
- Test: `tests/test_scorers.py`

**Interfaces:**
- Consumes: `Assessment`, `EvidenceBundle`.
- Produces: `grounding_score(assessment, bundle) -> float` (fraction of claims whose citation ∈ bundle urls; 1.0 if no claims) and `claims_resolve(assessment, bundle) -> bool` (all claim citations resolve). Golden set is a list of `{brief, expected_login}` for later precision scoring.

- [ ] **Step 1: Failing test**

```python
# tests/test_scorers.py
from sourcerer.evals.scorers import grounding_score, claims_resolve
from sourcerer.models import Candidate, Evidence, EvidenceBundle, Claim, Assessment
def _bundle():
    c = Candidate(login="x", profile_url="https://github.com/x")
    return c, EvidenceBundle(candidate=c, items=[Evidence(source_url="https://github.com/x/r", kind="github_repo", text="t")])
def test_fully_grounded_scores_one():
    c, b = _bundle()
    a = Assessment(candidate=c, fit_score=0.5, claims=[Claim(text="t", citation="https://github.com/x/r")], unverified=[], outreach_draft="")
    assert grounding_score(a, b) == 1.0 and claims_resolve(a, b) is True
def test_ungrounded_claim_lowers_score():
    c, b = _bundle()
    a = Assessment(candidate=c, fit_score=0.5, claims=[Claim(text="t", citation="https://evil.test")], unverified=[], outreach_draft="")
    assert grounding_score(a, b) == 0.0 and claims_resolve(a, b) is False
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement** (and write `evals/golden.json` = `[{"brief": {"role": "Rust systems engineer", "languages": ["rust"]}, "expected_login": "rustdev"}]`)

```python
# src/sourcerer/evals/scorers.py
from sourcerer.models import Assessment, EvidenceBundle

def grounding_score(assessment: Assessment, bundle: EvidenceBundle) -> float:
    if not assessment.claims:
        return 1.0
    urls = bundle.source_urls()
    grounded = sum(1 for c in assessment.claims if c.citation in urls)
    return grounded / len(assessment.claims)

def claims_resolve(assessment: Assessment, bundle: EvidenceBundle) -> bool:
    return grounding_score(assessment, bundle) == 1.0
```

- [ ] **Step 4: Run + commit**
```bash
git add src/sourcerer/evals tests/test_scorers.py evals/golden.json
git commit -m "feat: eval scorers (grounding) + golden set"
```

---

### Task 10: Tracing seam

**Files:**
- Create: `src/sourcerer/trace.py`
- Test: `tests/test_trace.py`

**Interfaces:**
- Produces: `traced(name:str, sink:list|None=None)` async context manager that appends a span `{"name","ms","ok"}` to the active sink; `use_sink(list)` to set a recording sink (default: in-memory `SPANS`); `get_spans() -> list`. (Langfuse export is a later phase; this is the portable seam.)

- [ ] **Step 1: Failing test**

```python
# tests/test_trace.py
from sourcerer.trace import traced, get_spans, reset_spans
async def test_span_recorded_with_name_and_ok():
    reset_spans()
    async with traced("research"):
        pass
    spans = get_spans()
    assert spans[-1]["name"] == "research" and spans[-1]["ok"] is True and spans[-1]["ms"] >= 0
async def test_span_marks_failure_and_reraises():
    reset_spans()
    try:
        async with traced("boom"):
            raise ValueError("x")
    except ValueError:
        pass
    assert get_spans()[-1] == {**get_spans()[-1], "name": "boom", "ok": False}
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**

```python
# src/sourcerer/trace.py
import time
from contextlib import asynccontextmanager
SPANS: list[dict] = []
def reset_spans() -> None: SPANS.clear()
def get_spans() -> list[dict]: return list(SPANS)

@asynccontextmanager
async def traced(name: str):
    start = time.perf_counter(); ok = True
    try:
        yield
    except Exception:
        ok = False; raise
    finally:
        SPANS.append({"name": name, "ms": round((time.perf_counter() - start) * 1000, 2), "ok": ok})
```

- [ ] **Step 4: Run + commit**
```bash
git add src/sourcerer/trace.py tests/test_trace.py
git commit -m "feat: tracing seam (in-memory spans)"
```

---

### Task 11: Pipeline + CLI (end-to-end, traced)

**Files:**
- Create: `src/sourcerer/pipeline.py`, `src/sourcerer/cli.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `async def run(brief, gh, fetcher, llm, model) -> list[Assessment]` (discover → for each candidate: research → synthesize; each stage wrapped in `traced`). `cli.main()` builds real clients from `config`, reads a brief (CLI flags), prints each assessment + its grounding score.

- [ ] **Step 1: Failing integration test (all mocks)**

```python
# tests/test_pipeline.py
import json
from sourcerer.pipeline import run
from sourcerer.models import Brief
from sourcerer.github import MockGitHub
from sourcerer.web import MockFetcher, PageContent
from sourcerer.llm import MockLLM
from sourcerer.research import research
from sourcerer.evals.scorers import grounding_score
from sourcerer.trace import reset_spans, get_spans
async def test_end_to_end_one_candidate_is_grounded():
    reset_spans()
    gh = MockGitHub(
        users=[{"login": "rustdev", "name": "Rusty", "html_url": "https://github.com/rustdev", "blog": "https://rusty.dev", "followers": 300, "bio": "systems"}],
        repos={"rustdev": [{"name": "fastdb", "language": "Rust", "stargazers_count": 900, "html_url": "https://github.com/rustdev/fastdb", "description": "embedded db"}]})
    fetcher = MockFetcher({"https://rusty.dev": PageContent(url="https://rusty.dev", title="Rusty", text="I build embedded Rust databases")})
    payload = json.dumps({"fit_score": 0.92,
        "claims": [{"text": "Authored fastdb, an embedded Rust DB", "citation": "https://github.com/rustdev/fastdb"}],
        "unverified": [], "outreach_draft": "Hi Rusty — loved fastdb..."})
    llm = MockLLM(lambda s, u: payload)
    results = await run(Brief(role="Rust systems engineer", languages=["rust"], max_candidates=1), gh, fetcher, llm, model="m")
    assert len(results) == 1
    bundle = await research(results[0].candidate, gh, fetcher)
    assert grounding_score(results[0], bundle) == 1.0
    assert results[0].claims[0].citation == "https://github.com/rustdev/fastdb"
    assert {"discover", "research", "synthesize"} <= {s["name"] for s in get_spans()}
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**

```python
# src/sourcerer/pipeline.py
from sourcerer.models import Brief, Assessment
from sourcerer.discovery import discover
from sourcerer.research import research
from sourcerer.synthesis import synthesize
from sourcerer.trace import traced

async def run(brief, gh, fetcher, llm, model) -> list[Assessment]:
    async with traced("discover"):
        candidates = await discover(brief, gh)
    out: list[Assessment] = []
    for cand in candidates:
        async with traced("research"):
            bundle = await research(cand, gh, fetcher)
        async with traced("synthesize"):
            out.append(await synthesize(cand, bundle, llm, model, voice=brief.voice))
    return out
```
```python
# src/sourcerer/cli.py
import argparse, asyncio
from sourcerer.config import get_settings
from sourcerer.models import Brief
from sourcerer.github import HttpGitHub
from sourcerer.web import HttpFetcher
from sourcerer.llm import LiteLLMClient
from sourcerer.pipeline import run
from sourcerer.evals.scorers import grounding_score
from sourcerer.research import research

async def _amain(brief: Brief) -> None:
    s = get_settings()
    gh, fetcher, llm = HttpGitHub(s.github_token), HttpFetcher(), LiteLLMClient()
    for a in await run(brief, gh, fetcher, llm, s.model):
        bundle = await research(a.candidate, gh, fetcher)  # re-derive for scoring display
        print(f"\n=== {a.candidate.name or a.candidate.login}  (fit {a.fit_score:.2f}, grounding {grounding_score(a, bundle):.2f}) ===")
        for c in a.claims:
            print(f"  • {c.text}  [{c.citation}]")
        if a.unverified:
            print("  unverified:", "; ".join(a.unverified))
        print("  ---\n  " + a.outreach_draft.replace("\n", "\n  "))

def main() -> None:
    p = argparse.ArgumentParser(prog="sourcerer")
    p.add_argument("role"); p.add_argument("--lang", action="append", default=[])
    p.add_argument("--topic", action="append", default=[]); p.add_argument("-n", "--max", type=int, default=1)
    a = p.parse_args()
    asyncio.run(_amain(Brief(role=a.role, languages=a.lang, topics=a.topic, max_candidates=a.max)))
```

- [ ] **Step 4: Run + commit**

Run: `pytest -v` (all tests) → PASS
```bash
git add src/sourcerer/pipeline.py src/sourcerer/cli.py tests/test_pipeline.py
git commit -m "feat: end-to-end pipeline + CLI (traced, grounded)"
```

---

## Phase 1 Done = 
`pytest` all green; `sourcerer "Rust systems engineer" --lang rust` runs end-to-end against real GitHub + a real LLM and prints a grounded, cited brief + outreach draft for one candidate, with spans recorded. **Deferred to later phases (own plans):** LangGraph orchestration + parallel fan-out, agentic browser (Browser Use/Stagehand), HITL review UI + send, pgvector memory, MCP server, guardrails/injection defense, cost router, durability, Langfuse export, and the reply-loop.
