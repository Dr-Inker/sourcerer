import json

from sourcerer.evals.scorers import grounding_score
from sourcerer.github import MockGitHub
from sourcerer.llm import MockLLM
from sourcerer.models import Brief
from sourcerer.pipeline import run, run_detailed
from sourcerer.trace import get_spans, reset_spans
from sourcerer.web import MockFetcher, PageContent


async def test_end_to_end_one_candidate_is_grounded():
    reset_spans()
    gh = MockGitHub(
        users=[{"login": "rustdev", "name": "Rusty", "html_url": "https://github.com/rustdev", "blog": "https://rusty.dev", "followers": 300, "bio": "systems"}],
        repos={"rustdev": [{"name": "fastdb", "language": "Rust", "stargazers_count": 900, "html_url": "https://github.com/rustdev/fastdb", "description": "embedded db"}]})
    fetcher = MockFetcher({"https://rusty.dev": PageContent(url="https://rusty.dev", title="Rusty", text="I build embedded Rust databases")})
    payload = json.dumps({"fit_score": 0.92,
        "claims": [{"text": "The fastdb repository describes an embedded db",
                    "citation": "https://github.com/rustdev/fastdb",
                    "supporting_quote": "embedded db"}],
        "unverified": [], "outreach_draft": "Hi Rusty — loved fastdb..."})
    llm = MockLLM(lambda s, u: payload)
    results = await run(Brief(role="Rust systems engineer", languages=["rust"], max_candidates=1), gh, fetcher, llm, model="m")
    assert len(results) == 1
    assessment, bundle = results[0]
    assert grounding_score(assessment, bundle) == 1.0
    assert assessment.claims[0].citation == "https://github.com/rustdev/fastdb"
    assert {"discover", "research", "synthesize"} <= {s["name"] for s in get_spans()}


async def test_run_isolates_a_candidate_whose_github_calls_fail():
    # Candidate "a" 403s during research; the batch must still return "b".
    reset_spans()
    gh = MockGitHub(
        users=[{"login": "a", "name": "A", "html_url": "https://github.com/a", "followers": 1},
               {"login": "b", "name": "B", "html_url": "https://github.com/b", "followers": 2}],
        repos={"a": [{"name": "ra", "html_url": "https://github.com/a/ra", "language": "Go"}],
               "b": [{"name": "rb", "html_url": "https://github.com/b/rb", "language": "Go"}]},
        fail_repos={"a"},
    )
    fetcher = MockFetcher({})
    payload = json.dumps({"fit_score": 0.7, "claims": [], "unverified": [], "outreach_draft": "hi"})
    llm = MockLLM(lambda s, u: payload)
    results = await run(Brief(role="Go dev", languages=["go"], max_candidates=2), gh, fetcher, llm, model="m")
    assert [a.candidate.login for a, _ in results] == ["b"]


async def test_run_isolates_a_candidate_whose_llm_call_raises_non_httpx():
    # LLM providers (LiteLLM) raise RateLimitError/APIError that are NOT httpx.HTTPError.
    # One candidate's provider failure must not sink the batch either.
    reset_spans()
    gh = MockGitHub(
        users=[{"login": "a", "name": "A", "html_url": "https://github.com/a"},
               {"login": "b", "name": "B", "html_url": "https://github.com/b"}],
        repos={"a": [], "b": []})
    fetcher = MockFetcher({})
    def responder(system, user):
        if "github.com/a" in user:
            raise RuntimeError("provider rate limit")  # stand-in for a non-httpx provider error
        return json.dumps({"fit_score": 0.6, "claims": [], "unverified": [], "outreach_draft": "hi"})
    llm = MockLLM(responder)
    results = await run(Brief(role="Go dev", languages=["go"], max_candidates=2), gh, fetcher, llm, model="m")
    assert [a.candidate.login for a, _ in results] == ["b"]


async def test_detailed_run_exposes_typed_candidate_failures():
    gh = MockGitHub(
        users=[{"login": "a", "html_url": "https://github.com/a", "bio": "Go developer"}],
        repos={}, fail_repos={"a"})
    report = await run_detailed(Brief(role="Go developer"), gh, MockFetcher({}),
                                MockLLM(lambda s, u: "{}"), model="m")
    assert report.results == []
    assert report.failures[0].login == "a"
    assert report.failures[0].stage == "research"
    assert report.failures[0].error_type == "HTTPStatusError"
