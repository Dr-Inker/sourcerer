import json

from sourcerer.demo.generate import (
    PRESETS,
    build_manifest,
    fixture_clients,
    generate_one,
    preset_to_brief,
    write_demo,
)
from sourcerer.demo.schema import DemoCandidate, DemoRun
from sourcerer.github import MockGitHub
from sourcerer.llm import MockLLM
from sourcerer.web import MockFetcher, PageContent


def test_all_shipped_fixtures_are_fictional_example_com():
    # The public demo must not depict real people: every persona/repo/blog URL is on the
    # RFC 2606 example.com placeholder domain, never a real github.com account.
    assert PRESETS, "expected shipped demo fixtures"
    for fx in PRESETS:
        p = fx["persona"]
        urls = [p["user"]["html_url"], p["blog"]["url"], *(r["html_url"] for r in p["repos"])]
        for u in urls:
            assert u.startswith("https://example.com/"), f"non-fictional URL in fixture {fx['slug']}: {u}"
        assert "github.com" not in " ".join(urls)


async def test_every_fixture_generates_a_clean_demo_run():
    for fx in PRESETS:
        gh, fetcher, llm = fixture_clients(fx)
        run = await generate_one(fx, gh, fetcher, llm, model="fixture", generated_at="t")
        assert run.candidate.profile_url.startswith("https://example.com/")
        # kept claims are all grounded; evidence is fictional only
        assert run.grounding_score == 1.0
        for ev in run.evidence:
            assert "github.com" not in ev.source_url


async def test_a_fixture_showcases_the_guard_demoting_a_fabrication():
    # At least one persona must demonstrate the load-bearing behaviour: a fabricated citation
    # demoted to 'unverified' with grounding_fidelity dropping below 1.0.
    demoted = []
    for fx in PRESETS:
        gh, fetcher, llm = fixture_clients(fx)
        run = await generate_one(fx, gh, fetcher, llm, model="fixture", generated_at="t")
        if run.grounding_fidelity is not None and run.grounding_fidelity < 1.0:
            demoted.append(run)
    assert demoted, "expected a fixture that showcases a demoted fabricated claim"
    assert demoted[0].unverified          # the fabricated claim landed in unverified
    assert demoted[0].grounding_score == 1.0  # yet the published brief stays fully grounded


def test_preset_to_brief_maps_role_and_languages():
    b = preset_to_brief({"slug": "x", "label": "X", "role": "Rust eng", "languages": ["rust"]})
    assert b.role == "Rust eng" and b.languages == ["rust"] and b.max_candidates == 1


def test_build_manifest_lists_all_presets():
    m = build_manifest(PRESETS)
    assert len(m["presets"]) == len(PRESETS)
    assert {"slug", "label", "role", "languages"} <= set(m["presets"][0].keys())


async def test_generate_one_with_mocks_produces_grounded_demo_run():
    preset = {"slug": "rust", "label": "Rust", "role": "Rust systems engineer", "languages": ["rust"]}
    gh = MockGitHub(
        users=[{"login": "rustdev", "name": "Rusty", "html_url": "https://github.com/rustdev",
                "blog": "https://rusty.dev", "followers": 300, "bio": "systems"}],
        repos={"rustdev": [{"name": "fastdb", "language": "Rust", "stargazers_count": 900,
                            "html_url": "https://github.com/rustdev/fastdb", "description": "embedded db"}]})
    fetcher = MockFetcher({"https://rusty.dev": PageContent(
        url="https://rusty.dev", title="Rusty", text="I build embedded Rust databases")})
    payload = json.dumps({"fit_score": 0.92,
        "claims": [{"text": "The repository describes an embedded db",
                    "citation": "https://github.com/rustdev/fastdb",
                    "supporting_quote": "embedded db"}],
        "unverified": [], "outreach_draft": "Hi Rusty"})
    run = await generate_one(preset, gh, fetcher, MockLLM(lambda s, u: payload),
                             model="m", generated_at="t")
    assert isinstance(run, DemoRun)
    assert run.candidate.login == "rustdev"
    assert run.grounding_score == 1.0
    assert {s.name for s in run.spans} >= {"discover", "research", "synthesize"}


def test_write_demo_writes_manifest_and_per_slug(tmp_path):
    run = DemoRun(role="r", languages=["rust"],
                  candidate=DemoCandidate(login="x", name=None, profile_url="https://github.com/x"),
                  fit_score=0.5, grounding_score=1.0, claims=[], unverified=[],
                  outreach_draft="hi", evidence=[], spans=[], model="m", generated_at="t")
    write_demo(tmp_path, {"rust": run},
               {"presets": [{"slug": "rust", "label": "Rust", "role": "r", "languages": ["rust"]}]})
    assert (tmp_path / "manifest.json").exists()
    assert json.loads((tmp_path / "rust.json").read_text())["candidate"]["login"] == "x"
    assert json.loads((tmp_path / "manifest.json").read_text())["presets"][0]["slug"] == "rust"


async def test_generate_one_raises_when_no_candidates():
    import pytest

    from sourcerer.demo.generate import generate_one
    from sourcerer.github import MockGitHub
    from sourcerer.llm import MockLLM
    from sourcerer.web import MockFetcher
    preset = {"slug": "empty", "label": "E", "role": "Nobody", "languages": ["cobol"]}
    with pytest.raises(ValueError):
        await generate_one(preset, MockGitHub(users=[], repos={}), MockFetcher({}),
                           MockLLM(lambda s, u: "{}"), model="m", generated_at="t")
