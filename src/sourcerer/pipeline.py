from sourcerer.models import Brief, Assessment
from sourcerer.discovery import discover
from sourcerer.research import research
from sourcerer.synthesis import synthesize
from sourcerer.trace import traced


async def run(brief, gh, fetcher, llm, model) -> list[Assessment]:
    async with traced("discover"):
        candidates = await discover(brief, gh)
    out: list[Assessment] = []
    for cand in candidates:
        async with traced("research"):
            bundle = await research(cand, gh, fetcher)
        async with traced("synthesize"):
            out.append(await synthesize(cand, bundle, llm, model, voice=brief.voice))
    return out
