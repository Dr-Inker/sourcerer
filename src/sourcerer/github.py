from typing import Protocol

import httpx


class GitHubClient(Protocol):
    async def search_users(self, query: str, limit: int) -> list[dict]: ...
    async def get_user(self, login: str) -> dict: ...
    async def list_repos(self, login: str, limit: int) -> list[dict]: ...
    async def list_paths(self, login: str, repo: str, default_branch: str, limit: int = 300) -> list[dict]: ...
    async def get_file(self, login: str, repo: str, path: str) -> str | None: ...


class MockGitHub:
    def __init__(self, users: list[dict], repos: dict[str, list[dict]],
                 trees: dict[str, list[dict]] | None = None,
                 files: dict[str, str] | None = None):
        self._users, self._repos = users, repos
        self._trees = trees or {}
        self._files = files or {}

    async def search_users(self, query: str, limit: int) -> list[dict]:
        return self._users[:limit]

    async def get_user(self, login: str) -> dict:
        return next(u for u in self._users if u["login"] == login)

    async def list_repos(self, login: str, limit: int) -> list[dict]:
        return self._repos.get(login, [])[:limit]

    async def list_paths(self, login: str, repo: str, default_branch: str, limit: int = 300) -> list[dict]:
        return self._trees.get(repo, [])[:limit]

    async def get_file(self, login: str, repo: str, path: str) -> str | None:
        return self._files.get(f"{repo}/{path}")


class HttpGitHub:
    def __init__(self, token: str | None):
        self._h = {"Authorization": f"Bearer {token}"} if token else {}

    async def search_users(self, query: str, limit: int) -> list[dict]:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(
                "https://api.github.com/search/users",
                params={"q": query, "per_page": limit},
                headers=self._h,
            )
            r.raise_for_status()
            items = r.json().get("items", [])
            return [await self.get_user(i["login"]) for i in items]

    async def get_user(self, login: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"https://api.github.com/users/{login}", headers=self._h)
            r.raise_for_status()
            return r.json()

    async def list_repos(self, login: str, limit: int) -> list[dict]:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(
                f"https://api.github.com/users/{login}/repos",
                params={"sort": "pushed", "per_page": limit},
                headers=self._h,
            )
            r.raise_for_status()
            return r.json()

    async def list_paths(self, login: str, repo: str, default_branch: str, limit: int = 300) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(
                    f"https://api.github.com/repos/{login}/{repo}/git/trees/{default_branch}",
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
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(
                    f"https://api.github.com/repos/{login}/{repo}/contents/{path}",
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
