import sys

from sourcerer import cli


def test_cli_maps_all_repeatable_brief_arguments(monkeypatch):
    captured = []

    async def fake_amain(brief):
        captured.append(brief)

    monkeypatch.setattr(cli, "_amain", fake_amain)
    monkeypatch.setattr(sys, "argv", [
        "sourcerer", "Rust systems engineer", "--lang", "rust",
        "--topic", "storage", "--must-have", "distributed databases", "--max", "3",
    ])
    cli.main()
    brief = captured[0]
    assert brief.role == "Rust systems engineer"
    assert brief.languages == ["rust"]
    assert brief.topics == ["storage"]
    assert brief.must_have == ["distributed databases"]
    assert brief.max_candidates == 3
