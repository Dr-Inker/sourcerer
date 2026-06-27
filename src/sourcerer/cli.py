import argparse, asyncio
from sourcerer.config import get_settings
from sourcerer.models import Brief
from sourcerer.github import HttpGitHub
from sourcerer.web import HttpFetcher
from sourcerer.llm import LiteLLMClient
from sourcerer.pipeline import run
from sourcerer.evals.scorers import grounding_score


async def _amain(brief: Brief) -> None:
    s = get_settings()
    gh, fetcher, llm = HttpGitHub(s.github_token), HttpFetcher(), LiteLLMClient()
    for assessment, bundle in await run(brief, gh, fetcher, llm, s.model):
        print(f"\n=== {assessment.candidate.name or assessment.candidate.login}  (fit {assessment.fit_score:.2f}, grounding {grounding_score(assessment, bundle):.2f}) ===")
        for c in assessment.claims:
            print(f"  • {c.text}  [{c.citation}]")
        if assessment.unverified:
            print("  unverified:", "; ".join(assessment.unverified))
        print("  ---\n  " + assessment.outreach_draft.replace("\n", "\n  "))


def main() -> None:
    p = argparse.ArgumentParser(prog="sourcerer")
    p.add_argument("role"); p.add_argument("--lang", action="append", default=[])
    p.add_argument("--topic", action="append", default=[]); p.add_argument("-n", "--max", type=int, default=1)
    a = p.parse_args()
    asyncio.run(_amain(Brief(role=a.role, languages=a.lang, topics=a.topic, max_candidates=a.max)))
