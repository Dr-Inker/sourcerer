from sourcerer.trace import traced, get_spans, reset_spans


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
