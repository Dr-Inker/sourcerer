import json
from sourcerer.github import MockGitHub
from sourcerer.web import MockFetcher, PageContent
from sourcerer.llm import MockLLM
from sourcerer.demo.schema import DemoRun, DemoCandidate
from sourcerer.demo.generate import (
    PRESETS, preset_to_brief, build_manifest, generate_one, write_demo,
)


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
        "claims": [{"text": "Authored fastdb", "citation": "https://github.com/rustdev/fastdb"}],
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
    from sourcerer.github import MockGitHub
    from sourcerer.web import MockFetcher
    from sourcerer.llm import MockLLM
    from sourcerer.demo.generate import generate_one
    preset = {"slug": "empty", "label": "E", "role": "Nobody", "languages": ["cobol"]}
    with pytest.raises(ValueError):
        await generate_one(preset, MockGitHub(users=[], repos={}), MockFetcher({}),
                           MockLLM(lambda s, u: "{}"), model="m", generated_at="t")
