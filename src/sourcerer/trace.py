import time
from contextlib import asynccontextmanager
from contextvars import ContextVar

# Spans live in a context-local buffer, not a process global, so concurrent runs (and the
# roadmapped long-lived MCP server / parallel fan-out) never interleave or leak into each other.
# Default None -> the first traced() call in a fresh context lazily binds its own list, which
# means separate asyncio tasks are isolated automatically.
_spans: ContextVar[list[dict] | None] = ContextVar("sourcerer_spans", default=None)


def _current() -> list[dict]:
    lst = _spans.get()
    if lst is None:
        lst = []
        _spans.set(lst)
    return lst


def reset_spans() -> None:
    _spans.set([])


def get_spans() -> list[dict]:
    return list(_current())


@asynccontextmanager
async def span_scope():
    """Bind a fresh span buffer for the duration — use once per run so a long-lived process
    doesn't accumulate spans across runs and concurrent runs stay isolated."""
    token = _spans.set([])
    try:
        yield
    finally:
        _spans.reset(token)


@asynccontextmanager
async def traced(name: str):
    start = time.perf_counter()
    ok = True
    try:
        yield
    except Exception:
        ok = False
        raise
    finally:
        _current().append(
            {"name": name, "ms": round((time.perf_counter() - start) * 1000, 2), "ok": ok}
        )
