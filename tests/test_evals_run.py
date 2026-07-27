from pathlib import Path

from sourcerer.evals.run import evaluate


async def test_shipped_retrieval_golden_set_meets_quality_floor():
    path = Path(__file__).resolve().parents[1] / "evals" / "golden.json"
    result = await evaluate(path)
    assert result["cases"] >= 4
    assert result["mrr"] >= 0.8
    assert result["top1_accuracy"] >= 0.75
