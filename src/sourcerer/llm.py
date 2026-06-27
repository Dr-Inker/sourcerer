from typing import Protocol, Callable


class LLMClient(Protocol):
    async def complete(self, system: str, user: str, model: str) -> str: ...


class MockLLM:
    def __init__(self, responder: Callable[[str, str], str]):
        self._responder = responder
        self.calls: list[dict] = []

    async def complete(self, system: str, user: str, model: str) -> str:
        self.calls.append({"system": system, "user": user, "model": model})
        return self._responder(system, user)


class LiteLLMClient:
    async def complete(self, system: str, user: str, model: str) -> str:
        import litellm

        resp = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        return resp["choices"][0]["message"]["content"]
