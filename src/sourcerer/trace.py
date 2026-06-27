import time
from contextlib import asynccontextmanager

SPANS: list[dict] = []


def reset_spans() -> None:
    SPANS.clear()


def get_spans() -> list[dict]:
    return list(SPANS)


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
        SPANS.append(
            {"name": name, "ms": round((time.perf_counter() - start) * 1000, 2), "ok": ok}
        )
