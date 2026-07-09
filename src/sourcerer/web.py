import asyncio
import ipaddress
from typing import Protocol
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse

import httpx
from selectolax.parser import HTMLParser
from pydantic import BaseModel


MAX_ROBOTS_BYTES = 64 * 1024


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


# NAT64 well-known + local-use prefixes: these are globally-routable-looking (is_global=True)
# but embed an IPv4 destination, so a gateway can reach internal hosts (e.g. 64:ff9b::7f00:1 = 127.0.0.1).
_NAT64_PREFIXES = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
)


def _ip_is_safe(ip: ipaddress._BaseAddress) -> bool:
    """A single resolved address is safe to fetch only if it is globally routable (which already
    excludes loopback/private/link-local/CGNAT/reserved/multicast) and is not a NAT64 prefix."""
    if not ip.is_global:
        return False
    return not any(ip.version == net.version and ip in net for net in _NAT64_PREFIXES)


class Fetcher(Protocol):
    async def fetch(self, url: str) -> PageContent | None: ...


class MockFetcher:
    def __init__(self, pages: dict[str, PageContent]):
        self._pages = pages

    async def fetch(self, url: str) -> PageContent | None:
        return self._pages.get(url)


class HttpFetcher:
    async def _resolve_validated(self, url: str) -> str | None:
        """Resolve the URL's host once, require EVERY resolved address to be public, and return
        one validated IP to pin the connection to. Returns None (fail closed) on any unsafe or
        unresolvable host. Pinning the returned IP for the actual connect closes the DNS-rebinding
        TOCTOU where a second, independent lookup at connect time could differ from this check."""
        host = urlparse(url).hostname
        if not host:
            return None
        # IP literal? classify directly (no DNS).
        try:
            ips = [ipaddress.ip_address(host)]
        except ValueError:
            try:
                infos = await asyncio.get_running_loop().getaddrinfo(host, None)
            except OSError:
                return None  # unresolvable -> fail closed
            ips = []
            for info in infos:
                try:
                    ips.append(ipaddress.ip_address(info[4][0]))
                except ValueError:
                    return None
            if not ips:
                return None
        if not all(_ip_is_safe(ip) for ip in ips):
            return None
        return str(ips[0])

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        # transport is an injection seam for tests (httpx.MockTransport); None = real network.
        self._transport = transport
        # One shared client per instance so robots + the page (+ redirect hops) reuse connections.
        self._client: httpx.AsyncClient | None = None

    def _c(self) -> httpx.AsyncClient:
        if self._client is None:
            # follow_redirects defaults False — we drive redirects manually to re-validate each hop.
            # max_keepalive_connections=0: don't pool connections across fetches. Because we connect
            # to a pinned IP, a keep-alive connection is keyed by IP, so two different blog hostnames
            # resolving to the same IP could otherwise reuse a tunnel whose cert was validated for the
            # other host's SNI. The fetcher makes few requests, so losing pooling costs ~nothing.
            self._client = httpx.AsyncClient(transport=self._transport,
                                             limits=httpx.Limits(max_keepalive_connections=0))
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "HttpFetcher":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def _resolve_is_public(self, url: str) -> bool:
        return await self._resolve_validated(url) is not None

    async def _pinned_get(self, url: str, ip: str, timeout: float) -> httpx.Response:
        """GET `url` but connect to the pre-validated `ip`, keeping Host + TLS SNI on the real
        host. Pinning the checked IP to the socket is what closes the DNS-rebinding TOCTOU."""
        u = httpx.URL(url)
        bracketed = f"[{u.host}]" if ":" in u.host else u.host   # RFC 7230 IPv6 literal
        host_header = bracketed + (f":{u.port}" if u.port is not None else "")
        extensions = {"sni_hostname": u.host} if u.scheme == "https" else {}
        return await self._c().get(
            u.copy_with(host=ip),
            headers={"User-Agent": "sourcerer/0.1", "Host": host_header},
            extensions=extensions,
            timeout=timeout,
        )

    async def _allowed(self, url: str, ip: str) -> bool:
        p = urlparse(url)
        robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        try:
            r = await self._pinned_get(robots_url, ip, timeout=10)
        except httpx.HTTPError:
            return True  # robots unreachable (timeout/conn error) → allowed
        if r.status_code >= 500:
            return False  # server error → be conservative (RFC 9309: treat as disallow)
        rules = r.text[:MAX_ROBOTS_BYTES].splitlines() if r.status_code == 200 else []
        rp.parse(rules)  # 4xx / no robots → empty ruleset → allow all
        return rp.can_fetch("sourcerer", url)

    async def fetch(self, url: str) -> PageContent | None:
        pinned = await self._resolve_validated(url)
        if pinned is None:
            return None
        if not await self._allowed(url, pinned):
            return None
        try:
            current, current_ip = url, pinned
            for _ in range(5):
                r = await self._pinned_get(current, current_ip, timeout=15)
                if r.is_redirect:
                    loc = r.headers.get("location")
                    if not loc:
                        return None
                    current = str(httpx.URL(current).join(loc))
                    current_ip = await self._resolve_validated(current)  # re-validate + re-pin each hop
                    if current_ip is None:
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
