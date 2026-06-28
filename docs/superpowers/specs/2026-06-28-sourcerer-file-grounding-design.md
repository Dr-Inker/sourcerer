# Sourcerer — file-path + key-content grounding

**Date:** 2026-06-28
**Status:** Approved (design), pending implementation plan
**Author:** dr.inker (with Claude)

## Problem

Sourcerer assesses an engineer's fit using evidence gathered in `research.py`. Today that
evidence is **repo metadata only**: for each of the candidate's top 5 repos it emits one
`Evidence(source_url=repo.html_url, kind="github_repo", text="name (lang, ★N): description")`
(`research.py:8-12`). The synthesis step already enforces **fail-closed citation membership** —
any claim whose `citation` is not in `bundle.source_urls()` is demoted to `unverified`
(`synthesis.py:36-45`).

Two consequences:

1. **Shallow grounding.** The LLM judges a candidate from one-line repo descriptions, then cites
   the repo URL. The claim is "grounded" (the URL is in the set) but the substance is unverified —
   we never showed the model any actual code or prose.
2. **The membership check has no fine-grained target.** There are no file paths in the source set,
   so the model cannot (and is never forced to) cite specific files, and fabricated file references
   cannot be caught because nothing operates at file granularity.

This is the gap identified by the "Karpathy repo lessons" review (item: rendergit `<source>` path-set
membership). The fix is to ingest repo **file paths and key file contents** as evidence, which both
deepens grounding and gives the existing membership check teeth.

## Goals / Non-goals

**Goals**
- Ingest each top repo's file tree and a small, capped set of key file contents (README + ≤3 notable
  files) as `Evidence`.
- Make those specific files **citable** (via blob URLs), so claims can ground in real code/prose and
  the membership check drops fabricated file references.
- Keep GLM token cost modest via tight caps (≈12 KB evidence text / candidate).
- No new dependencies; no schema change to `models.py`.

**Non-goals (YAGNI)**
- A separate span-support / NLI verification layer (membership stays the grounding mechanism here).
- Surfacing a per-repo "files skipped (reason)" report in the UI. We record timing only; skip-reason
  counts are deferred.
- Following the *literal* rendergit lesson of making the entire file tree citable (see Key Decision).

## Key Decision: only fetched files are citable (stronger than the literal lesson)

The literal lesson makes the **whole** file-tree path set citable. We deliberately do **not** do that.
Only files we actually fetched and placed in front of the model as `Evidence` (README + ≤3 notable
files) enter the citable set; the full tree is used **only** to *select* which files to fetch.

Rationale: Sourcerer's grounding **is** membership — there is no separate span-support layer. If every
real path were citable, the model could launder an ungrounded claim by citing a real-but-unread file
("expert in X, see `src/x.py`") and pass membership without us ever having shown that file. "Cite only
what you were shown" is tighter and composes correctly with content grounding.

## Architecture

Four source files change; one is new. Selection/caps logic is isolated in a new pure module so it is
unit-testable without network I/O.

### 1. `src/sourcerer/github.py` — two new client methods

Added to the `GitHubClient` Protocol and both `MockGitHub` and `HttpGitHub`:

- `async list_paths(login, repo, default_branch, limit=300) -> list[dict]`
  - `HttpGitHub`: `GET /repos/{login}/{repo}/git/trees/{default_branch}?recursive=1`.
  - Returns blob entries only, each `{"path": str, "size": int}` (filter `type == "blob"`), truncated
    to `limit`. On HTTP error returns `[]` (best-effort; never raises into research).
- `async get_file(login, repo, path) -> str | None`
  - `HttpGitHub`: `GET /repos/{login}/{repo}/contents/{path}` with header
    `Accept: application/vnd.github.raw`.
  - Returns `None` if: HTTP error, response bytes contain a null byte in the first 8 KB (binary), or
    UTF-8 decode fails. Otherwise returns the decoded text (un-truncated; caller truncates).

`MockGitHub` gains constructor params `trees: dict[str, list[dict]] | None` (keyed by repo name) and
`files: dict[str, str] | None` (keyed by `"{repo}/{path}"`), returning `[]` / `None` when absent.

### 2. `src/sourcerer/ingest.py` — NEW, pure helpers + policy constants

No network, no I/O — fully unit-testable.

Constants:
```
MAX_TREE_PATHS      = 300
FETCH_SIZE_CAP      = 64 * 1024     # don't fetch tree blobs larger than this
MAX_README_BYTES    = 3072
MAX_FILE_BYTES      = 1536
MAX_NOTABLE_FILES   = 3
MAX_TOTAL_EVIDENCE_BYTES = 12288    # per candidate, across README + notable files
BINARY_EXTENSIONS   = {png,jpg,jpeg,gif,svg,ico,pdf,zip,gz,tar,woff,woff2,ttf,eot,
                       so,dylib,dll,exe,bin,wasm,mp4,mp3,...}
SKIP_DIRS           = {node_modules, vendor, dist, build, third_party, deps, .git}
SKIP_FILE_PATTERNS  = {*.lock, *-lock.json, package-lock.json, yarn.lock,
                       pnpm-lock.yaml, *.min.js, *.min.css}
```

Functions:
- `find_readme(paths: list[dict]) -> str | None` — root-level file matching `README*`
  (case-insensitive); returns its path or `None`.
- `decide_file(path: str, size: int) -> str` — returns one of `ok | binary | too_large | vendored`
  (rendergit-style reason; `binary` by extension, `vendored` by SKIP_DIRS/SKIP_FILE_PATTERNS,
  `too_large` if `size > FETCH_SIZE_CAP`).
- `pick_notable(paths: list[dict], max_files=MAX_NOTABLE_FILES) -> list[str]` — candidates are blobs
  with `decide_file == "ok"` excluding the README; ranked by `(is_root desc, size desc, path asc)`
  (root-level files first, then larger, `path` as a stable deterministic tie-break); returns up to
  `max_files` paths.
- `blob_url(repo_html_url: str, default_branch: str, path: str) -> str` →
  `f"{repo_html_url}/blob/{default_branch}/{path}"`.
- `truncate(text: str, max_bytes: int) -> str` — byte-bounded truncation (UTF-8 safe).

### 3. `src/sourcerer/research.py` — expanded ingestion

For each repo in `await gh.list_repos(login, limit=5)`:
1. Append existing repo-metadata `Evidence` (unchanged).
2. Best-effort, inside a `traced("research.files")` span:
   - `tree = await gh.list_paths(login, repo["name"], repo["default_branch"])`.
   - README: if `find_readme(tree)`, `content = await gh.get_file(...)`; if content, append
     `Evidence(source_url=blob_url(...), kind="github_file", text=truncate(content, MAX_README_BYTES))`.
   - Notable: for each path in `pick_notable(tree)`, fetch + append
     `Evidence(kind="github_file", text=truncate(content, MAX_FILE_BYTES))`.
   - Stop adding file Evidence once cumulative appended file/README text reaches
     `MAX_TOTAL_EVIDENCE_BYTES` (repo metadata text does not count toward this cap).
3. Any exception from `list_paths`/`get_file` is swallowed for that repo — research always returns at
   least the metadata bundle (membership remains fail-closed downstream).

Blog fetch (`research.py:13-17`) is unchanged.

### 4. `src/sourcerer/synthesis.py` — prompt tweak only

No logic/schema change. The membership check at line 40 already operates over the enriched
`bundle.source_urls()`. Update `_system()` so the model knows file URLs are citable:

> "For every factual claim, cite the exact evidence `source_url` it comes from — this may be a repo
> URL, a specific file URL, or a web page; prefer the most specific source that supports the claim.
> If you cannot ground a statement in the evidence, put it in 'unverified'."

## Data flow

```
list_repos(5) ──► research.py
                     │  repo metadata Evidence            (existing)
                     ├─ list_paths ─► ingest.find_readme ─► get_file ─► Evidence(github_file, blob_url)
                     │                ingest.pick_notable ─► get_file ─► Evidence(github_file, blob_url)
                     │                (cap 12KB/candidate)
                     ▼
              EvidenceBundle.source_urls() = {repo urls} ∪ {fetched file blob urls} ∪ {blog url}
                     ▼
              synthesize() ─► LLM claims ─► keep iff citation ∈ source_urls() else → unverified
```

## Safety

- All GitHub fetches target `api.github.com` (fixed host) — no new SSRF surface. The existing SSRF
  guard protects the arbitrary-URL blog fetch (`web.py`) and is untouched.
- Membership stays fail-closed in synthesis.
- File ingestion is best-effort and never fails the pipeline.

## Testing (TDD)

- **`tests/test_ingest.py` (new)** — pure: `find_readme` (root, case-insensitive, absent); `decide_file`
  reasons (binary ext, vendored dir, lock/min pattern, too_large, ok); `pick_notable` (excludes README,
  drops vendored/binary/oversized, ranks root-then-size, caps at 3, deterministic order); `blob_url`
  shape; `truncate` byte bound + UTF-8 safety.
- **`tests/test_research.py` (extend)** — extend `MockGitHub` with `trees`/`files`; assert the bundle
  contains `github_file` Evidence with blob-URL `source_url`s, the README is included, vendored/lock
  files are absent, and total appended file text respects `MAX_TOTAL_EVIDENCE_BYTES`.
- **`tests/test_synthesis.py` (extend)** — core assertion via the existing mock-LLM pattern: a claim
  citing a **real** fetched blob URL is kept; a claim citing a **fabricated** file path (not in the
  bundle) is demoted to `unverified`.

## Files touched

| File | Change |
|------|--------|
| `src/sourcerer/github.py` | +`list_paths`, +`get_file` (Protocol + Mock + Http) |
| `src/sourcerer/ingest.py` | NEW — pure selection/caps helpers + constants |
| `src/sourcerer/research.py` | expanded ingestion, `traced` span, per-candidate cap |
| `src/sourcerer/synthesis.py` | one-line system-prompt tweak |
| `tests/test_ingest.py` | NEW |
| `tests/test_research.py` | extend MockGitHub + assertions |
| `tests/test_synthesis.py` | add fabricated-path case |

No new dependencies (`httpx` already used in `github.py`).
