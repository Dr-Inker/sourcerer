# tests/test_web.py
from sourcerer.web import HttpFetcher, MockFetcher, PageContent, extract_text


async def test_resolve_is_public_rejects_unsafe_ips():
    f = HttpFetcher()
    for url in [
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
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
