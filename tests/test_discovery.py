import httpx

from sourcerer.discovery import build_query, discover
from sourcerer.github import HttpGitHub, MockGitHub
from sourcerer.models import Brief


def test_build_query_includes_language_and_topics():
    q = build_query(Brief(role="x", languages=["rust"], topics=["databases"]))
    assert "language:rust" in q and "databases" in q


def test_build_query_includes_role_and_must_haves_and_is_bounded():
    q = build_query(Brief(role="Rust systems engineer", must_have=["distributed systems"]))
    assert '"Rust systems engineer"' in q
    assert '"distributed systems"' in q
    assert len(q) <= 256


async def test_discovery_reranks_profiles_against_the_complete_brief():
    users = [
        {"login": "popular", "html_url": "https://github.com/popular", "followers": 99,
         "bio": "frontend developer"},
        {"login": "relevant", "html_url": "https://github.com/relevant", "followers": 1,
         "bio": "Rust systems engineer building distributed databases"},
    ]
    candidates = await discover(
        Brief(role="Rust systems engineer", must_have=["distributed databases"], max_candidates=1),
        MockGitHub(users=users, repos={}),
    )
    assert [c.login for c in candidates] == ["relevant"]
    assert candidates[0].signals["discovery_score"] == 1.0


async def test_discover_maps_users_to_candidates():
    gh = MockGitHub(users=[{"login": "rustdev", "name": "Rusty", "html_url": "https://github.com/rustdev", "blog": "https://rusty.dev", "followers": 300}], repos={})
    cands = await discover(Brief(role="Rust eng", languages=["rust"], max_candidates=1), gh)
    assert cands[0].login == "rustdev" and cands[0].profile_url == "https://github.com/rustdev"
    assert cands[0].signals["blog"] == "https://rusty.dev"


async def test_discover_degrades_to_empty_when_search_rate_limited():
    # A 403 on the search call should yield no candidates, not a traceback.
    async with HttpGitHub(token=None, transport=httpx.MockTransport(lambda req: httpx.Response(403, request=req))) as gh:
        cands = await discover(Brief(role="x", languages=["rust"], max_candidates=1), gh)
    assert cands == []
