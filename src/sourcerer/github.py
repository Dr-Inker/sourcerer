from typing import Protocol

import httpx


class GitHubClient(Protocol):
    async def search_users(self, query: str, limit: int) -> list[dict]: ...
    async def get_user(self, login: str) -> dict: ...
    async def list_repos(self, login: str, limit: int) -> list[dict]: ...


class MockGitHub:
    def __init__(self, users: list[dict], repos: dict[str, list[dict]]):
        self._users, self._repos = users, repos

    async def search_users(self, query: str, limit: int) -> list[dict]:
        return self._users[:limit]

    async def get_user(self, login: str) -> dict:
        return next(u for u in self._users if u["login"] == login)

    async def list_repos(self, login: str, limit: int) -> list[dict]:
        return self._repos.get(login, [])[:limit]


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
