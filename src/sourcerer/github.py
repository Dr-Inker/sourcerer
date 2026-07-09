import asyncio
from typing import Protocol
from urllib.parse import quote

import httpx


class GitHubClient(Protocol):
    async def search_users(self, query: str, limit: int) -> list[dict]: ...
    async def get_user(self, login: str) -> dict: ...
    async def list_repos(self, login: str, limit: int) -> list[dict]: ...
    async def list_paths(self, login: str, repo: str, default_branch: str, limit: int = 300) -> list[dict]: ...
    async def get_file(self, login: str, repo: str, path: str) -> str | None: ...


def _http_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://api.github.com/")
    return httpx.HTTPStatusError(f"{status}", request=req, response=httpx.Response(status, request=req))


class MockGitHub:
    def __init__(self, users: list[dict], repos: dict[str, list[dict]],
                 trees: dict[str, list[dict]] | None = None,
                 files: dict[str, str] | None = None,
                 fail_repos: set[str] | None = None):
        self._users, self._repos = users, repos
        self._trees = trees or {}
        self._files = files or {}
        # logins whose list_repos should raise, to exercise error-isolation paths.
        self._fail_repos = fail_repos or set()

    async def search_users(self, query: str, limit: int) -> list[dict]:
        return self._users[:limit]

    async def get_user(self, login: str) -> dict:
        return next(u for u in self._users if u["login"] == login)

    async def list_repos(self, login: str, limit: int) -> list[dict]:
        if login in self._fail_repos:
            raise _http_error(403)
        return self._repos.get(login, [])[:limit]

    async def list_paths(self, login: str, repo: str, default_branch: str, limit: int = 300) -> list[dict]:
        return self._trees.get(repo, [])[:limit]

    async def get_file(self, login: str, repo: str, path: str) -> str | None:
        return self._files.get(f"{repo}/{path}")


class HttpGitHub:
    def __init__(self, token: str | None, transport: httpx.AsyncBaseTransport | None = None):
        self._h = {"Authorization": f"Bearer {token}"} if token else {}
        # transport is an injection seam for offline contract tests (httpx.MockTransport).
        self._transport = transport
        # One shared client per instance: connections to api.github.com are pooled/kept-alive
        # across the ~search + N-profile + per-repo calls a run makes (created lazily, closed on exit).
        self._client: httpx.AsyncClient | None = None

    def _c(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20, transport=self._transport)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "HttpGitHub":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def search_users(self, query: str, limit: int) -> list[dict]:
        r = await self._c().get(
            "https://api.github.com/search/users",
            params={"q": query, "per_page": limit},
            headers=self._h,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        # Fetch the full profiles concurrently; order preserved. Skip a profile we can't fetch
        # (httpx error), but re-raise anything else — cancellation and unexpected faults must not
        # be silently swallowed the way a per-profile HTTP failure is.
        results = await asyncio.gather(*(self.get_user(i["login"]) for i in items), return_exceptions=True)
        users: list[dict] = []
        for u in results:
            if isinstance(u, httpx.HTTPError):
                continue
            if isinstance(u, BaseException):
                raise u
            users.append(u)
        return users

    async def get_user(self, login: str) -> dict:
        r = await self._c().get(f"https://api.github.com/users/{login}", headers=self._h)
        r.raise_for_status()
        return r.json()

    async def list_repos(self, login: str, limit: int) -> list[dict]:
        r = await self._c().get(
            f"https://api.github.com/users/{login}/repos",
            params={"sort": "pushed", "per_page": limit},
            headers=self._h,
        )
        r.raise_for_status()
        return r.json()

    async def list_paths(self, login: str, repo: str, default_branch: str, limit: int = 300) -> list[dict]:
        try:
            r = await self._c().get(
                f"https://api.github.com/repos/{login}/{repo}/git/trees/{quote(default_branch, safe='/')}",
                params={"recursive": "1"},
                headers=self._h,
            )
            r.raise_for_status()
            tree = r.json().get("tree", [])
        except httpx.HTTPError:
            return []
        blobs = [{"path": t["path"], "size": t.get("size", 0)} for t in tree if t.get("type") == "blob"]
        return blobs[:limit]

    async def get_file(self, login: str, repo: str, path: str) -> str | None:
        try:
            r = await self._c().get(
                f"https://api.github.com/repos/{login}/{repo}/contents/{quote(path, safe='/')}",
                headers={**self._h, "Accept": "application/vnd.github.raw"},
            )
        except httpx.HTTPError:
            return None
        if r.status_code != 200:
            return None
        data = r.content
        if b"\x00" in data[:8192]:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None
