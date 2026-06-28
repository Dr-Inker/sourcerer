# Sourcerer File-Path + Key-Content Grounding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest each candidate repo's file paths plus README/notable file contents (capped) as `Evidence`, so assessments ground in real code and the fail-closed citation-membership check gains file-level teeth.

**Architecture:** A new pure module `ingest.py` holds all selection/caps logic (unit-testable, no I/O). `github.py` gains two best-effort client methods (`list_paths`, `get_file`). `research.py` orchestrates: per repo it lists the tree, fetches the README + ≤3 notable files via the pure selectors, and appends them as `Evidence` with blob-URL `source_url`s, respecting a per-candidate byte budget. `synthesis.py` is unchanged except a one-line system-prompt tweak — the existing membership check at `synthesis.py:40` already drops any claim citing a `source_url` not in the bundle, which now includes the fetched file URLs.

**Tech Stack:** Python ≥3.12, pydantic, httpx, pytest + pytest-asyncio (`asyncio_mode=auto`, `pythonpath=["src"]`). Test runner: `/opt/sourcerer/.venv/bin/python -m pytest`.

## Global Constraints

- Python `>=3.12`; **no new dependencies** (`httpx` is already used in `github.py`).
- Caps (exact): `MAX_TREE_PATHS=300`, `FETCH_SIZE_CAP=64*1024`, `MAX_README_BYTES=3072`, `MAX_FILE_BYTES=1536`, `MAX_NOTABLE_FILES=3`, `MAX_TOTAL_EVIDENCE_BYTES=12288` (README + notable file text per candidate; repo-metadata text does NOT count).
- **Only fetched files are citable** — do NOT add un-fetched tree paths to the evidence/source set. The full tree is used only to *select* files.
- Membership stays **fail-closed** in `synthesis.py` (a claim citing a `source_url` not in the bundle → `unverified`). Do not change that logic.
- File ingestion is **best-effort**: any `list_paths`/`get_file` error for a repo is swallowed; `research()` always returns at least repo-metadata + blog evidence.
- All GitHub fetches target `api.github.com` (fixed host) — no arbitrary-URL fetches, no new SSRF surface.
- File Evidence uses `kind="github_file"` and `source_url = blob_url(...)`.
- All tests are plain `async def test_*` (asyncio auto-mode); run from `/opt/sourcerer`.

---

### Task 1: `ingest.py` — pure selection/caps helpers

**Files:**
- Create: `src/sourcerer/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: nothing (pure, stdlib only: `fnmatch`, `posixpath`).
- Produces (relied on by Task 3):
  - Constants `MAX_TREE_PATHS, FETCH_SIZE_CAP, MAX_README_BYTES, MAX_FILE_BYTES, MAX_NOTABLE_FILES, MAX_TOTAL_EVIDENCE_BYTES`.
  - `find_readme(paths: list[dict]) -> str | None`
  - `decide_file(path: str, size: int) -> str` (one of `"ok"|"binary"|"too_large"|"vendored"`)
  - `pick_notable(paths: list[dict], max_files: int = MAX_NOTABLE_FILES) -> list[str]`
  - `blob_url(repo_html_url: str, default_branch: str, path: str) -> str`
  - `truncate(text: str, max_bytes: int) -> str`
  - `paths` items are dicts shaped `{"path": str, "size": int}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ingest.py`:

```python
from sourcerer import ingest


def test_find_readme_root_case_insensitive():
    paths = [{"path": "docs/README.md", "size": 10}, {"path": "ReadMe.rst", "size": 10}]
    assert ingest.find_readme(paths) == "ReadMe.rst"


def test_find_readme_absent_returns_none():
    assert ingest.find_readme([{"path": "src/main.py", "size": 10}]) is None


def test_decide_file_reasons():
    assert ingest.decide_file("src/main.py", 100) == "ok"
    assert ingest.decide_file("logo.png", 100) == "binary"
    assert ingest.decide_file("node_modules/x/index.js", 100) == "vendored"
    assert ingest.decide_file("yarn.lock", 100) == "vendored"
    assert ingest.decide_file("app.min.js", 100) == "vendored"
    assert ingest.decide_file("big.py", ingest.FETCH_SIZE_CAP + 1) == "too_large"


def test_pick_notable_excludes_readme_vendored_binary_and_caps():
    paths = [
        {"path": "README.md", "size": 200},
        {"path": "engine.py", "size": 5000},
        {"path": "util.py", "size": 1000},
        {"path": "src/deep.py", "size": 9000},
        {"path": "yarn.lock", "size": 8000},
        {"path": "logo.png", "size": 8000},
    ]
    got = ingest.pick_notable(paths)
    assert "README.md" not in got
    assert "yarn.lock" not in got
    assert "logo.png" not in got
    assert len(got) == 3
    # root-level first (engine.py before util.py by size), then nested deep.py
    assert got == ["engine.py", "util.py", "src/deep.py"]


def test_blob_url_shape():
    assert ingest.blob_url("https://github.com/u/r", "main", "src/a.py") == \
        "https://github.com/u/r/blob/main/src/a.py"
    # trailing slash on repo url is normalized
    assert ingest.blob_url("https://github.com/u/r/", "main", "a.py") == \
        "https://github.com/u/r/blob/main/a.py"


def test_truncate_byte_bound_is_utf8_safe():
    assert ingest.truncate("hello", 100) == "hello"
    out = ingest.truncate("h" * 50, 10)
    assert len(out.encode("utf-8")) <= 10
    # never raises on a multibyte boundary cut
    multi = "é" * 20  # 2 bytes each
    assert len(ingest.truncate(multi, 5).encode("utf-8")) <= 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/sourcerer/.venv/bin/python -m pytest tests/test_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sourcerer.ingest'`.

- [ ] **Step 3: Write the implementation**

Create `src/sourcerer/ingest.py`:

```python
import fnmatch
import posixpath

MAX_TREE_PATHS = 300
FETCH_SIZE_CAP = 64 * 1024
MAX_README_BYTES = 3072
MAX_FILE_BYTES = 1536
MAX_NOTABLE_FILES = 3
MAX_TOTAL_EVIDENCE_BYTES = 12288

BINARY_EXTENSIONS = frozenset({
    "png", "jpg", "jpeg", "gif", "svg", "ico", "bmp", "webp", "pdf", "zip", "gz",
    "tar", "tgz", "bz2", "7z", "rar", "woff", "woff2", "ttf", "eot", "otf", "so",
    "dylib", "dll", "exe", "bin", "wasm", "class", "jar", "mp4", "mp3", "mov",
    "avi", "wav", "flac", "ogg", "webm", "pyc", "o", "a", "lib", "dat", "db", "sqlite",
})
SKIP_DIRS = frozenset({
    "node_modules", "vendor", "dist", "build", "third_party", "deps", ".git",
    "target", ".venv", "__pycache__",
})
SKIP_FILE_PATTERNS = (
    "*.lock", "*-lock.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "*.min.js", "*.min.css",
)


def _ext(path: str) -> str:
    base = posixpath.basename(path)
    dot = base.rfind(".")
    return base[dot + 1:].lower() if dot > 0 else ""


def find_readme(paths: list[dict]) -> str | None:
    for p in paths:
        path = p["path"]
        if "/" not in path and path.lower().startswith("readme"):
            return path
    return None


def decide_file(path: str, size: int) -> str:
    parts = path.split("/")
    if any(d in SKIP_DIRS for d in parts[:-1]):
        return "vendored"
    base = parts[-1]
    if any(fnmatch.fnmatch(base, pat) for pat in SKIP_FILE_PATTERNS):
        return "vendored"
    if _ext(path) in BINARY_EXTENSIONS:
        return "binary"
    if size > FETCH_SIZE_CAP:
        return "too_large"
    return "ok"


def pick_notable(paths: list[dict], max_files: int = MAX_NOTABLE_FILES) -> list[str]:
    readme = find_readme(paths)
    cands = [
        p for p in paths
        if p["path"] != readme and decide_file(p["path"], p.get("size", 0)) == "ok"
    ]
    # root-level first (False<True), then larger first, then path for stable order
    cands.sort(key=lambda p: ("/" in p["path"], -p.get("size", 0), p["path"]))
    return [p["path"] for p in cands[:max_files]]


def blob_url(repo_html_url: str, default_branch: str, path: str) -> str:
    return f"{repo_html_url.rstrip('/')}/blob/{default_branch}/{path}"


def truncate(text: str, max_bytes: int) -> str:
    b = text.encode("utf-8")
    if len(b) <= max_bytes:
        return text
    return b[:max_bytes].decode("utf-8", errors="ignore")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/opt/sourcerer/.venv/bin/python -m pytest tests/test_ingest.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git -C /opt/sourcerer add src/sourcerer/ingest.py tests/test_ingest.py
git -C /opt/sourcerer commit -m "feat(ingest): pure file selection + caps helpers"
```

---

### Task 2: `github.py` — `list_paths` + `get_file` client methods

**Files:**
- Modify: `src/sourcerer/github.py` (Protocol, `MockGitHub`, `HttpGitHub`)
- Test: `tests/test_github.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces (relied on by Task 3):
  - `async list_paths(login: str, repo: str, default_branch: str, limit: int = 300) -> list[dict]` — returns `[{"path","size"}]` blobs only, `[]` on error.
  - `async get_file(login: str, repo: str, path: str) -> str | None` — text or `None` (error/binary/decode-fail).
  - `MockGitHub.__init__(users, repos, trees=None, files=None)` where `trees: dict[repo_name -> list[{"path","size"}]]`, `files: dict["{repo}/{path}" -> str]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_github.py`:

```python
async def test_mock_list_paths_and_get_file():
    gh = MockGitHub(
        users=[],
        repos={"rustdev": [{"name": "fastdb", "html_url": "https://github.com/rustdev/fastdb", "default_branch": "main"}]},
        trees={"fastdb": [{"path": "README.md", "size": 12}, {"path": "src/a.rs", "size": 30}]},
        files={"fastdb/README.md": "hello"},
    )
    paths = await gh.list_paths("rustdev", "fastdb", "main")
    assert {p["path"] for p in paths} == {"README.md", "src/a.rs"}
    assert await gh.get_file("rustdev", "fastdb", "README.md") == "hello"
    assert await gh.get_file("rustdev", "fastdb", "missing.txt") is None
    # unknown repo -> empty tree, not an error
    assert await gh.list_paths("rustdev", "nope", "main") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/sourcerer/.venv/bin/python -m pytest tests/test_github.py::test_mock_list_paths_and_get_file -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'trees'`.

- [ ] **Step 3: Write the implementation**

In `src/sourcerer/github.py`, add to the `GitHubClient` Protocol (after `list_repos`):

```python
    async def list_paths(self, login: str, repo: str, default_branch: str, limit: int = 300) -> list[dict]: ...
    async def get_file(self, login: str, repo: str, path: str) -> str | None: ...
```

Replace `MockGitHub.__init__` and add the two methods:

```python
class MockGitHub:
    def __init__(self, users: list[dict], repos: dict[str, list[dict]],
                 trees: dict[str, list[dict]] | None = None,
                 files: dict[str, str] | None = None):
        self._users, self._repos = users, repos
        self._trees = trees or {}
        self._files = files or {}

    async def search_users(self, query: str, limit: int) -> list[dict]:
        return self._users[:limit]

    async def get_user(self, login: str) -> dict:
        return next(u for u in self._users if u["login"] == login)

    async def list_repos(self, login: str, limit: int) -> list[dict]:
        return self._repos.get(login, [])[:limit]

    async def list_paths(self, login: str, repo: str, default_branch: str, limit: int = 300) -> list[dict]:
        return self._trees.get(repo, [])[:limit]

    async def get_file(self, login: str, repo: str, path: str) -> str | None:
        return self._files.get(f"{repo}/{path}")
```

Add to `HttpGitHub` (after `list_repos`):

```python
    async def list_paths(self, login: str, repo: str, default_branch: str, limit: int = 300) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(
                    f"https://api.github.com/repos/{login}/{repo}/git/trees/{default_branch}",
                    params={"recursive": "1"},
                    headers=self._h,
                )
                r.raise_for_status()
                tree = r.json().get("tree", [])
        except httpx.HTTPError:
            return []
        blobs = [{"path": t["path"], "size": t.get("size", 0)} for t in tree if t.get("type") == "blob"]
        return blobs[:limit]

    async def get_file(self, login: str, repo: str, path: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(
                    f"https://api.github.com/repos/{login}/{repo}/contents/{path}",
                    headers={**self._h, "Accept": "application/vnd.github.raw"},
                )
        except httpx.HTTPError:
            return None
        if r.status_code != 200:
            return None
        data = r.content
        if b"\x00" in data[:8192]:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/opt/sourcerer/.venv/bin/python -m pytest tests/test_github.py -v`
Expected: PASS (both the existing test and the new one).

- [ ] **Step 5: Commit**

```bash
git -C /opt/sourcerer add src/sourcerer/github.py tests/test_github.py
git -C /opt/sourcerer commit -m "feat(github): list_paths + get_file (best-effort, binary-safe)"
```

---

### Task 3: `research.py` — ingest file paths + contents with caps

**Files:**
- Modify: `src/sourcerer/research.py`
- Test: `tests/test_research.py`

**Interfaces:**
- Consumes: Task 1 (`ingest.*`), Task 2 (`gh.list_paths`, `gh.get_file`), `trace.traced`.
- Produces: `research()` bundle now includes `Evidence(kind="github_file", source_url=blob_url(...))` items; signature unchanged: `async research(candidate, gh, fetcher) -> EvidenceBundle`.

- [ ] **Step 1: Write the failing tests**

Add to the imports at the top of `tests/test_research.py`:

```python
from sourcerer import ingest
```

Append these tests:

```python
async def test_research_ingests_file_paths_and_contents_skipping_vendored():
    cand = Candidate(login="rustdev", name="Rusty", profile_url="https://github.com/rustdev")
    repo = {"name": "fastdb", "language": "Rust", "stargazers_count": 900,
            "html_url": "https://github.com/rustdev/fastdb", "description": "embedded db",
            "default_branch": "main"}
    trees = {"fastdb": [
        {"path": "README.md", "size": 200},
        {"path": "engine.rs", "size": 5000},
        {"path": "util.rs", "size": 1000},
        {"path": "yarn.lock", "size": 9000},
        {"path": "logo.png", "size": 4000},
    ]}
    files = {
        "fastdb/README.md": "fastdb is an embedded database",
        "fastdb/engine.rs": "fn engine() {}",
        "fastdb/util.rs": "fn util() {}",
    }
    gh = MockGitHub(users=[], repos={"rustdev": [repo]}, trees=trees, files=files)
    bundle = await research(cand, gh, MockFetcher({}))
    urls = bundle.source_urls()
    assert "https://github.com/rustdev/fastdb/blob/main/README.md" in urls
    assert "https://github.com/rustdev/fastdb/blob/main/engine.rs" in urls
    assert not any("yarn.lock" in u for u in urls)
    assert not any("logo.png" in u for u in urls)
    assert any(e.kind == "github_file" for e in bundle.items)


async def test_research_respects_total_evidence_byte_cap():
    cand = Candidate(login="rustdev", name="Rusty", profile_url="https://github.com/rustdev")
    big = "x" * 5000
    repos = [{"name": f"r{i}", "html_url": f"https://github.com/rustdev/r{i}",
              "default_branch": "main"} for i in range(5)]
    trees = {f"r{i}": [{"path": "README.md", "size": 5000},
                        {"path": "a.py", "size": 5000},
                        {"path": "b.py", "size": 5000},
                        {"path": "c.py", "size": 5000}] for i in range(5)}
    files = {f"r{i}/{p}": big for i in range(5) for p in ["README.md", "a.py", "b.py", "c.py"]}
    gh = MockGitHub(users=[], repos={"rustdev": repos}, trees=trees, files=files)
    bundle = await research(cand, gh, MockFetcher({}))
    total = sum(len(e.text.encode("utf-8")) for e in bundle.items if e.kind == "github_file")
    assert total <= ingest.MAX_TOTAL_EVIDENCE_BYTES


async def test_research_missing_default_branch_falls_back_to_head():
    # the original repo fixture has no default_branch -> must not KeyError
    cand = Candidate(login="rustdev", name="Rusty", profile_url="https://github.com/rustdev")
    gh = MockGitHub(users=[], repos={"rustdev": [
        {"name": "fastdb", "language": "Rust", "stargazers_count": 900,
         "html_url": "https://github.com/rustdev/fastdb", "description": "embedded db"}]})
    bundle = await research(cand, gh, MockFetcher({}))
    assert any(e.kind == "github_repo" for e in bundle.items)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/sourcerer/.venv/bin/python -m pytest tests/test_research.py -v`
Expected: the two new content tests FAIL (no `github_file` evidence / blob URLs absent). `test_research_missing_default_branch_falls_back_to_head` PASSES already (regression guard).

- [ ] **Step 3: Write the implementation**

Replace the entire contents of `src/sourcerer/research.py`:

```python
from sourcerer.models import Candidate, Evidence, EvidenceBundle
from sourcerer.github import GitHubClient
from sourcerer.web import Fetcher
from sourcerer.trace import traced
from sourcerer import ingest


async def _ingest_repo_files(gh: GitHubClient, login: str, repo: dict, budget: list[int]) -> list[Evidence]:
    """Best-effort: README + <=3 notable files for one repo, honoring the shared byte budget."""
    branch = repo.get("default_branch") or "HEAD"
    name = repo["name"]
    try:
        tree = await gh.list_paths(login, name, branch)
    except Exception:
        return []
    targets: list[tuple[str, int]] = []
    readme = ingest.find_readme(tree)
    if readme:
        targets.append((readme, ingest.MAX_README_BYTES))
    for path in ingest.pick_notable(tree):
        targets.append((path, ingest.MAX_FILE_BYTES))

    items: list[Evidence] = []
    for path, cap in targets:
        if budget[0] <= 0:
            break
        try:
            content = await gh.get_file(login, name, path)
        except Exception:
            continue
        if not content:
            continue
        text = ingest.truncate(content, min(cap, budget[0]))
        budget[0] -= len(text.encode("utf-8"))
        items.append(Evidence(
            source_url=ingest.blob_url(repo["html_url"], branch, path),
            kind="github_file", text=text,
        ))
    return items


async def research(candidate: Candidate, gh: GitHubClient, fetcher: Fetcher) -> EvidenceBundle:
    items: list[Evidence] = []
    budget = [ingest.MAX_TOTAL_EVIDENCE_BYTES]
    for repo in await gh.list_repos(candidate.login, limit=5):
        items.append(Evidence(
            source_url=repo["html_url"], kind="github_repo",
            text=f'{repo["name"]} ({repo.get("language")}, ★{repo.get("stargazers_count",0)}): {repo.get("description") or ""}',
        ))
        async with traced("research.files"):
            items.extend(await _ingest_repo_files(gh, candidate.login, repo, budget))
    blog = candidate.signals.get("blog")
    if blog:
        page = await fetcher.fetch(blog)
        if page:
            items.append(Evidence(source_url=page.url, kind="web_page", text=f"{page.title}: {page.text}"))
    return EvidenceBundle(candidate=candidate, items=items)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/opt/sourcerer/.venv/bin/python -m pytest tests/test_research.py -v`
Expected: PASS (original + 3 new tests).

- [ ] **Step 5: Commit**

```bash
git -C /opt/sourcerer add src/sourcerer/research.py tests/test_research.py
git -C /opt/sourcerer commit -m "feat(research): ingest repo file paths + capped file contents"
```

---

### Task 4: `synthesis.py` — prompt invites file citations; lock fabricated-path drop

**Files:**
- Modify: `src/sourcerer/synthesis.py:14-21` (`_system`)
- Test: `tests/test_synthesis.py`

**Interfaces:**
- Consumes: Task 3 (bundles now carry `github_file` blob-URL evidence).
- Produces: no signature change; `_system()` text now mentions a "file URL" as a citable source.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_synthesis.py`:

```python
async def test_system_prompt_invites_file_url_citations():
    cand = Candidate(login="x", name="X", profile_url="https://github.com/x")
    bundle = EvidenceBundle(candidate=cand, items=[
        Evidence(source_url="https://github.com/x/r", kind="github_repo", text="r")])
    payload = json.dumps({"fit_score": 0.0, "claims": [], "unverified": [], "outreach_draft": ""})
    llm = MockLLM(lambda s, u: payload)
    await synthesize(cand, bundle, llm, model="m")
    assert "file URL" in llm.calls[0]["system"]


async def test_fabricated_file_path_dropped_real_one_kept():
    cand = Candidate(login="rustdev", name="Rusty", profile_url="https://github.com/rustdev")
    real = "https://github.com/rustdev/fastdb/blob/main/engine.rs"
    bundle = EvidenceBundle(candidate=cand, items=[
        Evidence(source_url=real, kind="github_file", text="fn engine() {}")])
    payload = json.dumps({"fit_score": 0.8, "claims": [
        {"text": "Wrote the storage engine", "citation": real},
        {"text": "Wrote the query planner",
         "citation": "https://github.com/rustdev/fastdb/blob/main/planner.rs"},
    ], "unverified": [], "outreach_draft": "Hi"})
    a = await synthesize(cand, bundle, MockLLM(lambda s, u: payload), model="m")
    assert [c.text for c in a.claims] == ["Wrote the storage engine"]
    assert "Wrote the query planner" in a.unverified
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/sourcerer/.venv/bin/python -m pytest tests/test_synthesis.py -v`
Expected: `test_system_prompt_invites_file_url_citations` FAILS (`"file URL"` not in prompt). `test_fabricated_file_path_dropped_real_one_kept` PASSES already (existing membership logic) — it is a behavior-lock guard.

- [ ] **Step 3: Write the implementation**

Replace `_system` in `src/sourcerer/synthesis.py`:

```python
def _system(voice: str) -> str:
    return (
        "You assess a software engineer's fit for the SOUGHT ROLE described in the user message, using ONLY the supplied evidence. "
        "For every factual claim you make, cite the exact evidence source_url it comes from — this may be a repo URL, a specific file URL, or a web page; prefer the most specific source that supports the claim. "
        "If you cannot ground a statement in the evidence, put it in 'unverified' — never assert it as a claim. "
        f"Write the outreach in this voice: {voice}. "
        'Respond ONLY with JSON: {"fit_score":<0..1>,"claims":[{"text":"","citation":"<source_url>"}],"unverified":[],"outreach_draft":""}'
    )
```

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `/opt/sourcerer/.venv/bin/python -m pytest -v`
Expected: PASS (all prior tests + the new ones; nothing regressed).

- [ ] **Step 5: Commit**

```bash
git -C /opt/sourcerer add src/sourcerer/synthesis.py tests/test_synthesis.py
git -C /opt/sourcerer commit -m "feat(synthesis): invite file-URL citations; lock fabricated-path drop"
```

---

## Self-Review

**Spec coverage:**
- `github.py` `list_paths`/`get_file` → Task 2. ✓
- `ingest.py` pure helpers + constants → Task 1. ✓
- `research.py` expanded ingestion, `traced` span, per-candidate cap, best-effort → Task 3. ✓
- `synthesis.py` prompt tweak → Task 4. ✓
- Only-fetched-files-citable (no un-fetched tree paths added to evidence) → Task 3 only appends Evidence for fetched README/notable files. ✓
- Membership fail-closed unchanged → Task 4 leaves `synthesis.py:36-45` logic intact. ✓
- Tests: `test_ingest.py` (T1), `test_research.py` (T3), `test_synthesis.py` (T4) + `test_github.py` (T2). ✓
- Transparency skip-reason report → intentionally out-of-scope (spec Non-goals); `traced("research.files")` gives timing only. ✓

**Placeholder scan:** none — every code/test step shows complete content; commands have expected output.

**Type consistency:** `paths` items are `{"path","size"}` everywhere; `list_paths(login, repo, default_branch, limit)` and `get_file(login, repo, path)` signatures identical across Protocol/Mock/Http/research; `blob_url(repo_html_url, default_branch, path)` used consistently; `budget` is a one-element `list[int]` shared mutable in T3. ✓
