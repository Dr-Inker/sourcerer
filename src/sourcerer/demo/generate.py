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
