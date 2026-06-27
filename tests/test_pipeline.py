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
