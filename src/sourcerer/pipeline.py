import sys

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
        try:
            async with traced("research"):
                bundle = await research(cand, gh, fetcher)
            async with traced("synthesize"):
                assessment = await synthesize(cand, bundle, llm, model, brief=brief)
        except Exception as e:
            # Isolate per candidate: a GitHub rate-limit, a network error, or an LLM-provider
            # error (LiteLLM's RateLimitError/APIError are NOT httpx.HTTPError) on one candidate
            # must not sink the batch. Surfaced to stderr so failures aren't silent.
            print(f"warning: skipping candidate {cand.login}: {e!r}", file=sys.stderr)
            continue
        out.append((assessment, bundle))
    return out
