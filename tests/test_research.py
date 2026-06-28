from sourcerer.research import research
from sourcerer.models import Candidate
from sourcerer.github import MockGitHub
from sourcerer.web import MockFetcher, PageContent
from sourcerer import ingest


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
