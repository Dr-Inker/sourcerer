import argparse, asyncio
from sourcerer.config import get_settings
from sourcerer.models import Brief
from sourcerer.github import HttpGitHub
from sourcerer.web import HttpFetcher
from sourcerer.llm import LiteLLMClient
from sourcerer.pipeline import run
from sourcerer.evals.scorers import grounding_score
from sourcerer.research import research


async def _amain(brief: Brief) -> None:
    s = get_settings()
    gh, fetcher, llm = HttpGitHub(s.github_token), HttpFetcher(), LiteLLMClient()
    for a in await run(brief, gh, fetcher, llm, s.model):
        bundle = await research(a.candidate, gh, fetcher)  # re-derive for scoring display
        print(f"\n=== {a.candidate.name or a.candidate.login}  (fit {a.fit_score:.2f}, grounding {grounding_score(a, bundle):.2f}) ===")
        for c in a.claims:
            print(f"  • {c.text}  [{c.citation}]")
        if a.unverified:
            print("  unverified:", "; ".join(a.unverified))
        print("  ---\n  " + a.outreach_draft.replace("\n", "\n  "))


def main() -> None:
    p = argparse.ArgumentParser(prog="sourcerer")
    p.add_argument("role"); p.add_argument("--lang", action="append", default=[])
    p.add_argument("--topic", action="append", default=[]); p.add_argument("-n", "--max", type=int, default=1)
    a = p.parse_args()
    asyncio.run(_amain(Brief(role=a.role, languages=a.lang, topics=a.topic, max_candidates=a.max)))
