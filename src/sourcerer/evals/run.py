import argparse
import asyncio
import json
from pathlib import Path

from sourcerer.discovery import discover
from sourcerer.evals.scorers import reciprocal_rank
from sourcerer.github import MockGitHub
from sourcerer.models import Brief


async def evaluate(path: Path) -> dict[str, float | int]:
    cases = json.loads(path.read_text())
    reciprocal_ranks: list[float] = []
    top_one = 0
    for case in cases:
        brief = Brief.model_validate(case["brief"])
        candidates = await discover(brief, MockGitHub(users=case["users"], repos={}))
        ranked = [candidate.login for candidate in candidates]
        rr = reciprocal_rank(ranked, case["expected_login"])
        reciprocal_ranks.append(rr)
        top_one += bool(ranked and ranked[0] == case["expected_login"])
    count = len(cases)
    return {
        "cases": count,
        "mrr": sum(reciprocal_ranks) / count if count else 0.0,
        "top1_accuracy": top_one / count if count else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic retrieval golden set")
    parser.add_argument("--golden", type=Path,
                        default=Path(__file__).resolve().parents[3] / "evals" / "golden.json")
    parser.add_argument("--min-mrr", type=float, default=0.8)
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.golden))
    print(json.dumps(result, sort_keys=True))
    if result["mrr"] < args.min_mrr:
        raise SystemExit(f"MRR {result['mrr']:.3f} is below required {args.min_mrr:.3f}")


if __name__ == "__main__":
    main()
