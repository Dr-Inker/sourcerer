import pytest
from sourcerer.llm import MockLLM


async def test_mock_records_calls_and_returns():
    m = MockLLM(lambda system, user: '{"ok": true}')
    out = await m.complete(system="s", user="u", model="x")
    assert out == '{"ok": true}'
    assert m.calls[0] == {"system": "s", "user": "u", "model": "x"}
