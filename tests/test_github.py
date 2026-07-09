import asyncio

import httpx
import pytest

from sourcerer.github import MockGitHub, HttpGitHub


async def test_mock_search_and_repos():
    gh = MockGitHub(
        users=[{"login": "rustdev", "name": "Rusty", "html_url": "https://github.com/rustdev", "blog": "https://rusty.dev", "bio": "systems"}],
        repos={"rustdev": [{"name": "fastdb", "language": "Rust", "stargazers_count": 900, "html_url": "https://github.com/rustdev/fastdb", "description": "embedded db"}]},
    )
    assert (await gh.search_users("language:rust", 5))[0]["login"] == "rustdev"
    assert (await gh.list_repos("rustdev", 5))[0]["language"] == "Rust"


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


async def test_http_github_context_manager_opens_and_closes_client():
    # A shared client is created lazily on first use and closed on context exit (connection reuse).
    def handler(request):
        return httpx.Response(200, json={"login": "x", "html_url": "https://example.com/x"}, request=request)
    gh = HttpGitHub(token=None, transport=httpx.MockTransport(handler))
    assert gh._client is None
    async with gh:
        await gh.get_user("x")
        assert gh._client is not None
    assert gh._client is None


async def test_search_users_preserves_fanout_order():
    # gather preserves the search order of the returned profiles.
    def handler(request):
        p = request.url.path
        if p == "/search/users":
            return httpx.Response(200, json={"items": [{"login": "a"}, {"login": "b"}, {"login": "c"}]}, request=request)
        login = p.rsplit("/", 1)[-1]
        return httpx.Response(200, json={"login": login, "html_url": f"https://example.com/{login}"}, request=request)
    async with HttpGitHub(token=None, transport=httpx.MockTransport(handler)) as gh:
        users = await gh.search_users("q", 5)
    assert [u["login"] for u in users] == ["a", "b", "c"]


async def test_search_users_fans_out_concurrently():
    # Deterministic proof of concurrency: each profile handler blocks until ALL profile
    # requests are in flight. A sequential fan-out would leave only one in flight and the
    # barrier would time out; only a concurrent gather lets all arrive and release.
    n = 3
    inflight = 0
    all_started = asyncio.Event()
    async def handler(request):
        nonlocal inflight
        if request.url.path == "/search/users":
            return httpx.Response(200, json={"items": [{"login": f"u{i}"} for i in range(n)]}, request=request)
        inflight += 1
        if inflight >= n:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=2)
        login = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json={"login": login, "html_url": f"https://example.com/{login}"}, request=request)
    async with HttpGitHub(token=None, transport=httpx.MockTransport(handler)) as gh:
        users = await gh.search_users("q", 5)
    assert {u["login"] for u in users} == {"u0", "u1", "u2"}


async def test_search_users_propagates_non_http_errors_from_fanout():
    # A non-HTTP error (bug, or a malformed-JSON decode) must NOT be silently swallowed the way
    # an httpx error is — only unfetchable profiles are skipped; other faults propagate.
    class BuggyGitHub(HttpGitHub):
        async def get_user(self, login: str) -> dict:
            if login == "b":
                raise RuntimeError("bug in profile handling")
            return {"login": login, "html_url": f"https://example.com/{login}"}
    def handler(request):
        return httpx.Response(200, json={"items": [{"login": "a"}, {"login": "b"}]}, request=request)
    async with BuggyGitHub(token=None, transport=httpx.MockTransport(handler)) as gh:
        with pytest.raises(RuntimeError):
            await gh.search_users("q", 5)


async def test_http_search_users_skips_a_failing_profile_fetch():
    # The search->profile fan-out must not abort the whole search when one profile 403s.
    def handler(request):
        p = request.url.path
        if p == "/search/users":
            return httpx.Response(200, json={"items": [{"login": "good"}, {"login": "bad"}]}, request=request)
        if p == "/users/good":
            return httpx.Response(200, json={"login": "good", "html_url": "https://github.com/good"}, request=request)
        return httpx.Response(403, request=request)  # /users/bad rate-limited
    async with HttpGitHub(token=None, transport=httpx.MockTransport(handler)) as gh:
        users = await gh.search_users("q", 5)
    assert [u["login"] for u in users] == ["good"]
