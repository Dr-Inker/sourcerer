from sourcerer.models import Brief, Assessment, EvidenceBundle
from sourcerer.discovery import discover
from sourcerer.research import research
from sourcerer.synthesis import synthesize
from sourcerer.trace import traced


async def run(brief, gh, fetcher, llm, model) -> list[tuple[Assessment, EvidenceBundle]]:
    async with traced("discover"):
        candidates = await discover(brief, gh)
    out: list[tuple[Assessment, EvidenceBundle]] = []
    for cand in candidates:
        async with traced("research"):
            bundle = await research(cand, gh, fetcher)
        async with traced("synthesize"):
            assessment = await synthesize(cand, bundle, llm, model, brief=brief)
        out.append((assessment, bundle))
    return out
