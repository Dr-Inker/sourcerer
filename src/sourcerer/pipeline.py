import asyncio
import sys
from dataclasses import dataclass, field

from sourcerer.discovery import discover
from sourcerer.models import Assessment, EvidenceBundle
from sourcerer.research import research
from sourcerer.synthesis import synthesize
from sourcerer.trace import traced


@dataclass(frozen=True)
class CandidateFailure:
    login: str
    stage: str
    error_type: str
    message: str


@dataclass
class RunReport:
    results: list[tuple[Assessment, EvidenceBundle]] = field(default_factory=list)
    failures: list[CandidateFailure] = field(default_factory=list)


async def run_detailed(brief, gh, fetcher, llm, model, concurrency: int = 4) -> RunReport:
    async with traced("discover"):
        candidates = await discover(brief, gh)
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def process(cand):
        stage = "research"
        try:
            async with semaphore:
                async with traced("research"):
                    bundle = await research(cand, gh, fetcher)
                stage = "synthesize"
                async with traced("synthesize"):
                    assessment = await synthesize(cand, bundle, llm, model, brief=brief)
        except Exception as e:
            print(f"warning: skipping candidate {cand.login}: {e!r}", file=sys.stderr)
            return CandidateFailure(login=cand.login, stage=stage,
                                    error_type=type(e).__name__, message=str(e)[:500])
        return assessment, bundle

    outcomes = await asyncio.gather(*(process(cand) for cand in candidates))
    report = RunReport()
    for outcome in outcomes:
        if isinstance(outcome, CandidateFailure):
            report.failures.append(outcome)
        else:
            report.results.append(outcome)
    return report


async def run(brief, gh, fetcher, llm, model) -> list[tuple[Assessment, EvidenceBundle]]:
    """Compatibility API. Use run_detailed when operational failure data matters."""
    return (await run_detailed(brief, gh, fetcher, llm, model)).results
