# tests/test_web.py
import asyncio
import socket

import httpx

from sourcerer.web import HttpFetcher, MockFetcher, PageContent, extract_text

PUBLIC = "93.184.216.34"


def _allow_robots(request):
    """Any handler helper: answer robots.txt with an empty (allow-all) body."""
    return httpx.Response(200, text="", request=request) if request.url.path == "/robots.txt" else None


async def test_fetch_pins_validated_ip_not_a_reresolved_name(monkeypatch):
    # Resolve example.com -> a public IP, then prove the actual connection targets THAT IP
    # (with Host + SNI kept on the hostname) — i.e. no second, rebindable DNS lookup at connect.
    loop = asyncio.get_running_loop()
    async def fake_gai(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC, 0))]
    monkeypatch.setattr(loop, "getaddrinfo", fake_gai)
    seen = {}
    def handler(request):
        r = _allow_robots(request)
        if r is not None:
            return r
        seen["host"] = request.url.host
        seen["host_header"] = request.headers.get("Host")
        seen["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, text="<title>T</title><body>hello world</body>", request=request)
    f = HttpFetcher(transport=httpx.MockTransport(handler))
    page = await f.fetch("https://example.com/p")
    assert page is not None and "hello world" in page.text
    assert seen["host"] == PUBLIC              # connected to the validated IP
    assert seen["host_header"] == "example.com"
    assert seen["sni"] == "example.com"        # TLS SNI/cert check stays on the real host


async def test_fetch_blocks_redirect_to_private_ip():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="", request=request)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"}, request=request)
    f = HttpFetcher(transport=httpx.MockTransport(handler))
    assert await f.fetch("http://93.184.216.34/start") is None
    assert not any("169.254" in u for u in calls)   # the private target was never requested


async def test_fetch_returns_none_on_redirect_without_location():
    def handler(request):
        r = _allow_robots(request)
        return r if r is not None else httpx.Response(302, request=request)
    f = HttpFetcher(transport=httpx.MockTransport(handler))
    assert await f.fetch("http://93.184.216.34/x") is None


async def test_fetch_gives_up_after_too_many_redirects():
    def handler(request):
        r = _allow_robots(request)
        return r if r is not None else httpx.Response(302, headers={"location": "http://93.184.216.34/next"}, request=request)
    f = HttpFetcher(transport=httpx.MockTransport(handler))
    assert await f.fetch("http://93.184.216.34/start") is None


async def test_robots_5xx_is_conservative_and_disallows():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(503, request=request)
        return httpx.Response(200, text="<body>x</body>", request=request)
    f = HttpFetcher(transport=httpx.MockTransport(handler))
    assert await f.fetch("http://93.184.216.34/p") is None


async def test_resolve_is_public_rejects_unsafe_ips():
    f = HttpFetcher()
    for url in [
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://100.64.0.1/",                 # RFC 6598 carrier-grade NAT (was allowed under old denylist)
        "http://[64:ff9b::7f00:1]/",          # NAT64 embedding 127.0.0.1 (is_global=True, must still be blocked)
        "http://[::ffff:169.254.169.254]/",   # IPv4-mapped cloud metadata
    ]:
        assert await f._resolve_is_public(url) is False
    assert await f._resolve_is_public("http://8.8.8.8/") is True


async def test_mock_fetch_returns_known_page():
    p = PageContent(url="https://rusty.dev", title="Rusty", text="I love embedded Rust")
    f = MockFetcher({"https://rusty.dev": p})
    assert (await f.fetch("https://rusty.dev")).text == "I love embedded Rust"
    assert await f.fetch("https://missing.dev") is None


def test_extract_text_strips_markup():
    html = "<html><head><title>T</title></head><body><h1>Hi</h1><script>x</script><p>world</p></body></html>"
    title, text = extract_text(html)
    assert title == "T" and "Hi" in text and "world" in text and "x" not in text
