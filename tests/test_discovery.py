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
