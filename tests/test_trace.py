import asyncio

from sourcerer.trace import traced, get_spans, reset_spans, span_scope


async def test_span_recorded_with_name_and_ok():
    reset_spans()
    async with traced("research"):
        pass
    spans = get_spans()
    assert spans[-1]["name"] == "research" and spans[-1]["ok"] is True and spans[-1]["ms"] >= 0


async def test_span_marks_failure_and_reraises():
    reset_spans()
    try:
        async with traced("boom"):
            raise ValueError("x")
    except ValueError:
        pass
    assert get_spans()[-1] == {**get_spans()[-1], "name": "boom", "ok": False}


async def test_concurrent_runs_do_not_interleave_spans():
    # Two runs racing in separate tasks must each see only their own spans.
    async def worker(tag):
        async with span_scope():
            async with traced(f"{tag}-1"):
                await asyncio.sleep(0.01)
            async with traced(f"{tag}-2"):
                pass
            return sorted(s["name"] for s in get_spans())
    a, b = await asyncio.gather(worker("A"), worker("B"))
    assert a == ["A-1", "A-2"]
    assert b == ["B-1", "B-2"]
