import asyncio
import ipaddress
from typing import Protocol
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse

import httpx
from selectolax.parser import HTMLParser
from pydantic import BaseModel


class PageContent(BaseModel):
    url: str
    title: str
    text: str


def extract_text(html: str) -> tuple[str, str]:
    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript"):
        tag.decompose()
    title = (tree.css_first("title").text() if tree.css_first("title") else "").strip()
    body = tree.body.text(separator=" ", strip=True) if tree.body else ""
    return title, " ".join(body.split())


class Fetcher(Protocol):
    async def fetch(self, url: str) -> PageContent | None: ...


class MockFetcher:
    def __init__(self, pages: dict[str, PageContent]):
        self._pages = pages

    async def fetch(self, url: str) -> PageContent | None:
        return self._pages.get(url)


class HttpFetcher:
    async def _resolve_is_public(self, url: str) -> bool:
        host = urlparse(url).hostname
        if not host:
            return False
        # IP literal? classify directly (no DNS).
        try:
            ips = [ipaddress.ip_address(host)]
        except ValueError:
            try:
                infos = await asyncio.get_running_loop().getaddrinfo(host, None)
            except OSError:
                return False  # unresolvable -> fail closed
            ips = []
            for info in infos:
                try:
                    ips.append(ipaddress.ip_address(info[4][0]))
                except ValueError:
                    return False
            if not ips:
                return False
        return all(not (ip.is_loopback or ip.is_private or ip.is_link_local
                        or ip.is_reserved or ip.is_multicast or ip.is_unspecified)
                   for ip in ips)

    async def _allowed(self, url: str) -> bool:
        p = urlparse(url)
        rp = RobotFileParser()
        rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(rp.url)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except httpx.HTTPError:
            return True  # no robots reachable → allowed
        return rp.can_fetch("sourcerer", url)

    async def fetch(self, url: str) -> PageContent | None:
        if not await self._resolve_is_public(url):
            return None
        if not await self._allowed(url):
            return None
        try:
            async with httpx.AsyncClient(timeout=15) as c:   # follow_redirects defaults False
                current = url
                for _ in range(5):
                    r = await c.get(current, headers={"User-Agent": "sourcerer/0.1"})
                    if r.is_redirect:
                        loc = r.headers.get("location")
                        if not loc:
                            return None
                        current = str(httpx.URL(current).join(loc))
                        if not await self._resolve_is_public(current):
                            return None
                        continue
                    r.raise_for_status()
                    break
                else:
                    return None  # too many redirects
        except httpx.HTTPError:
            return None
        title, text = extract_text(r.text)
        return PageContent(url=url, title=title, text=text[:8000])
