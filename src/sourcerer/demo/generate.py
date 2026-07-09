import asyncio
import json
from pathlib import Path

from sourcerer.models import Brief
from sourcerer.github import MockGitHub, GitHubClient
from sourcerer.web import MockFetcher, PageContent, Fetcher
from sourcerer.llm import MockLLM, LLMClient
from sourcerer.pipeline import run
from sourcerer.trace import reset_spans, get_spans, span_scope
from sourcerer import ingest
from sourcerer.demo.schema import DemoRun, to_demo_run

# The PUBLIC demo depicts FICTIONAL personas only — every URL is on the RFC 2606 example.com
# placeholder domain, so no real person or repository is researched, scored, or shown. The real
# pipeline (discover -> research -> synthesize + the fail-closed grounding guard) runs end-to-end
# over deterministic mock clients seeded with this invented data, so generation is offline, free,
# and reproducible by anyone (no API keys). To research real, public candidates, use the CLI.
MODEL_LABEL = "illustrative fixture (offline)"

PRESETS: list[dict] = [
    {
        "slug": "rust-systems-engineer", "label": "Rust systems engineer",
        "role": "Rust systems engineer", "languages": ["rust"],
        "persona": {
            "user": {"login": "tessa-embedded", "name": "Tessa Ferro (sample persona)",
                     "html_url": "https://example.com/gh/tessa-embedded",
                     "blog": "https://example.com/blog/tessa", "followers": 812,
                     "bio": "embedded & storage engines in Rust"},
            "repos": [{"name": "tessellate", "language": "Rust", "stargazers_count": 812,
                       "html_url": "https://example.com/gh/tessa-embedded/tessellate",
                       "description": "an embedded, log-structured key-value store", "default_branch": "main"}],
            "trees": {"tessellate": [{"path": "README.md", "size": 900}, {"path": "src/engine.rs", "size": 1400}]},
            "files": {"tessellate/README.md": "# tessellate\nA small embedded log-structured KV store with crash-safe writes and a Rust-native API.",
                      "tessellate/src/engine.rs": "pub struct Engine { /* WAL + LSM compaction */ }"},
            "blog": {"url": "https://example.com/blog/tessa", "title": "Designing a crash-safe WAL",
                     "text": "Notes on building a write-ahead log and compaction for an embedded Rust database."},
            "fit_score": 0.9,
            "outreach": "Hi Tessa — tessellate's crash-safe WAL and LSM compaction line up closely with what we're building. Would you be open to a short chat?",
            "claims": [
                {"text": "Authors tessellate, an embedded log-structured KV store in Rust", "cite": "repo"},
                {"text": "Implemented a crash-safe write-ahead log and LSM compaction", "cite": "readme"},
                {"text": "Writes about WAL and compaction design for embedded databases", "cite": "blog"},
            ],
        },
    },
    {
        "slug": "deep-learning-engineer", "label": "Deep-learning (LLM) engineer",
        "role": "Deep learning and LLM engineer", "languages": ["python"],
        "persona": {
            "user": {"login": "ravi-ml-sample", "name": "Ravi Chandran (sample persona)",
                     "html_url": "https://example.com/gh/ravi-ml-sample",
                     "blog": "https://example.com/blog/ravi", "followers": 1503,
                     "bio": "training infra for language models"},
            "repos": [{"name": "gradient-garden", "language": "Python", "stargazers_count": 1503,
                       "html_url": "https://example.com/gh/ravi-ml-sample/gradient-garden",
                       "description": "a compact library for distributed LLM fine-tuning", "default_branch": "main"}],
            "trees": {"gradient-garden": [{"path": "README.md", "size": 1000}, {"path": "gg/trainer.py", "size": 1600}]},
            "files": {"gradient-garden/README.md": "# gradient-garden\nCompact utilities for data-parallel LLM fine-tuning with gradient checkpointing.",
                      "gradient-garden/gg/trainer.py": "class Trainer:  # ZeRO-style sharded optimizer state\n    ..."},
            "blog": {"url": "https://example.com/blog/ravi", "title": "Sharding optimizer state",
                     "text": "A walk through data-parallel fine-tuning and gradient checkpointing tradeoffs."},
            "fit_score": 0.86,
            "outreach": "Hi Ravi — gradient-garden's take on sharded optimizer state is exactly the area we're hiring for. Open to comparing notes?",
            # This persona demonstrates the guard: the last claim cites a file that was never
            # gathered (a fabricated source), so it is demoted to 'unverified' and fidelity drops.
            "claims": [
                {"text": "Authors gradient-garden, a distributed LLM fine-tuning library", "cite": "repo"},
                {"text": "Implements gradient checkpointing and sharded optimizer state", "cite": "readme"},
                {"text": "Led the PyTorch distributed team at a major lab", "cite": "fabricated"},
            ],
        },
    },
    {
        "slug": "go-cloud-native", "label": "Go / cloud-native engineer",
        "role": "Go cloud-native and distributed-systems engineer", "languages": ["go"],
        "persona": {
            "user": {"login": "mara-cloud", "name": "Mara Ilic (sample persona)",
                     "html_url": "https://example.com/gh/mara-cloud",
                     "blog": "https://example.com/blog/mara", "followers": 640,
                     "bio": "service meshes & control planes in Go"},
            "repos": [{"name": "flock", "language": "Go", "stargazers_count": 640,
                       "html_url": "https://example.com/gh/mara-cloud/flock",
                       "description": "a lightweight service mesh control plane", "default_branch": "main"}],
            "trees": {"flock": [{"path": "README.md", "size": 800}, {"path": "internal/xds/server.go", "size": 1500}]},
            "files": {"flock/README.md": "# flock\nA small service-mesh control plane speaking xDS to Envoy sidecars.",
                      "flock/internal/xds/server.go": "package xds // streaming xDS discovery server"},
            "blog": {"url": "https://example.com/blog/mara", "title": "xDS from scratch",
                     "text": "Building a streaming xDS control plane and reconciling sidecar state."},
            "fit_score": 0.88,
            "outreach": "Hi Mara — flock's xDS control plane is right in our wheelhouse. Would you be up for a conversation?",
            "claims": [
                {"text": "Authors flock, a service-mesh control plane in Go", "cite": "repo"},
                {"text": "Built a streaming xDS discovery server for Envoy sidecars", "cite": "readme"},
                {"text": "Writes about reconciling sidecar state via xDS", "cite": "blog"},
            ],
        },
    },
    {
        "slug": "open-source-js-ts", "label": "Open-source JS/TS engineer",
        "role": "Open-source JavaScript / TypeScript engineer", "languages": ["typescript"],
        "persona": {
            "user": {"login": "devon-ts", "name": "Devon Park (sample persona)",
                     "html_url": "https://example.com/gh/devon-ts",
                     "blog": "https://example.com/blog/devon", "followers": 2210,
                     "bio": "type-safe styling & DX tooling"},
            "repos": [{"name": "prismstyle", "language": "TypeScript", "stargazers_count": 2210,
                       "html_url": "https://example.com/gh/devon-ts/prismstyle",
                       "description": "a zero-runtime, type-safe CSS-in-TS library", "default_branch": "main"}],
            "trees": {"prismstyle": [{"path": "README.md", "size": 1100}, {"path": "src/extract.ts", "size": 1300}]},
            "files": {"prismstyle/README.md": "# prismstyle\nZero-runtime, fully type-safe CSS-in-TS with compile-time extraction.",
                      "prismstyle/src/extract.ts": "export function extract(/* AST -> static CSS */) {}"},
            "blog": {"url": "https://example.com/blog/devon", "title": "Zero-runtime styling",
                     "text": "How compile-time extraction removes the runtime cost of CSS-in-TS."},
            "fit_score": 0.84,
            "outreach": "Hi Devon — prismstyle's compile-time extraction is a great fit for our DX work. Open to chatting?",
            "claims": [
                {"text": "Authors prismstyle, a zero-runtime type-safe CSS-in-TS library", "cite": "repo"},
                {"text": "Implements compile-time CSS extraction from the type-checked AST", "cite": "readme"},
                {"text": "Writes about removing the runtime cost of CSS-in-TS", "cite": "blog"},
            ],
        },
    },
]


def preset_to_brief(preset: dict) -> Brief:
    return Brief(role=preset["role"], languages=list(preset["languages"]), max_candidates=1)


def build_manifest(presets: list[dict]) -> dict:
    return {"presets": [
        {"slug": p["slug"], "label": p["label"], "role": p["role"], "languages": list(p["languages"])}
        for p in presets
    ]}


def _authored_response(preset: dict) -> str:
    """Build the fixture's deterministic LLM reply, resolving each claim's `cite` tag to the
    actual in-bundle evidence URL (or a fabricated one, to exercise the demotion path)."""
    p = preset["persona"]
    repo = p["repos"][0]
    branch = repo.get("default_branch") or "HEAD"
    repo_url = repo["html_url"]
    urls = {
        "repo": repo_url,
        "readme": ingest.blob_url(repo_url, branch, "README.md"),
        "blog": p["blog"]["url"],
        "fabricated": ingest.blob_url(repo_url, branch, "internal/never-gathered.md"),
    }
    claims = [{"text": c["text"], "citation": urls[c["cite"]]} for c in p["claims"]]
    return json.dumps({"fit_score": p["fit_score"], "claims": claims,
                       "unverified": [], "outreach_draft": p["outreach"]})


def fixture_clients(preset: dict) -> tuple[GitHubClient, Fetcher, LLMClient]:
    """Deterministic mock clients seeded with one fictional persona — the whole pipeline runs
    against these, so no network or API key is needed to (re)generate the public demo."""
    p = preset["persona"]
    user = p["user"]
    gh = MockGitHub(users=[user], repos={user["login"]: p["repos"]},
                    trees=p["trees"], files=p["files"])
    blog = p["blog"]
    fetcher = MockFetcher({blog["url"]: PageContent(url=blog["url"], title=blog["title"], text=blog["text"])})
    resp = _authored_response(preset)
    llm = MockLLM(lambda s, u, resp=resp: resp)
    return gh, fetcher, llm


async def generate_one(preset: dict, gh: GitHubClient, fetcher: Fetcher, llm: LLMClient,
                       model: str, generated_at: str) -> DemoRun:
    brief = preset_to_brief(preset)
    reset_spans()
    results = await run(brief, gh, fetcher, llm, model)
    if not results:
        raise ValueError(f"no candidates discovered for preset {preset['slug']!r}")
    assessment, bundle = results[0]
    return to_demo_run(brief, assessment, bundle, get_spans(), model, generated_at)


def write_demo(out_dir: Path, runs: dict[str, DemoRun], manifest: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for slug, demo_run in runs.items():
        (out_dir / f"{slug}.json").write_text(demo_run.model_dump_json(indent=2))


async def main() -> None:
    import datetime
    generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    runs: dict[str, DemoRun] = {}
    for preset in PRESETS:
        async with span_scope():
            gh, fetcher, llm = fixture_clients(preset)
            runs[preset["slug"]] = await generate_one(preset, gh, fetcher, llm, MODEL_LABEL, generated_at)
        print(f"generated {preset['slug']}")
    out_dir = Path(__file__).resolve().parents[3] / "web" / "demo"
    write_demo(out_dir, runs, build_manifest(PRESETS))
    print(f"wrote {len(runs)} fictional demo runs + manifest to {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
