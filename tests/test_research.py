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
