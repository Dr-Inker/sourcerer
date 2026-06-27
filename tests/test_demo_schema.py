import json
from sourcerer.models import Brief, Candidate, Evidence, EvidenceBundle, Claim, Assessment
from sourcerer.demo.schema import to_demo_run, DemoRun


def _fixture():
    cand = Candidate(login="rustdev", name="Rusty", profile_url="https://github.com/rustdev")
    bundle = EvidenceBundle(candidate=cand, items=[
        Evidence(source_url="https://github.com/rustdev/fastdb", kind="github_repo",
                 text="fastdb (Rust, ★900): embedded db"),
        Evidence(source_url="https://rusty.dev", kind="web_page",
                 text="Rusty: I build embedded Rust databases"),
    ])
    assessment = Assessment(
        candidate=cand, fit_score=0.92,
        claims=[Claim(text="Authored fastdb", citation="https://github.com/rustdev/fastdb")],
        unverified=["Worked at BigCo"], outreach_draft="Hi Rusty",
    )
    brief = Brief(role="Rust systems engineer", languages=["rust"])
    spans = [
        {"name": "discover", "ms": 12.0, "ok": True},
        {"name": "research", "ms": 30.0, "ok": True},
        {"name": "synthesize", "ms": 50.0, "ok": True},
    ]
    return brief, assessment, bundle, spans


def test_to_demo_run_captures_grounding_and_replay_fields():
    brief, assessment, bundle, spans = _fixture()
    run = to_demo_run(brief, assessment, bundle, spans,
                      model="openrouter/z-ai/glm-5.1", generated_at="2026-06-27T12:00:00Z")
    assert run.role == "Rust systems engineer"
    assert run.languages == ["rust"]
    assert run.candidate.login == "rustdev"
    assert run.fit_score == 0.92
    assert run.grounding_score == 1.0  # the sole claim's citation is in the bundle
    assert run.claims[0].citation == "https://github.com/rustdev/fastdb"
    assert run.unverified == ["Worked at BigCo"]
    assert [s.name for s in run.spans] == ["discover", "research", "synthesize"]
    assert len(run.evidence) == 2 and run.evidence[0].kind == "github_repo"
    assert run.model == "openrouter/z-ai/glm-5.1"
    assert run.generated_at == "2026-06-27T12:00:00Z"


def test_demo_run_json_round_trips():
    brief, assessment, bundle, spans = _fixture()
    run = to_demo_run(brief, assessment, bundle, spans, model="m", generated_at="t")
    data = json.loads(run.model_dump_json())
    assert data["claims"][0]["citation"] == "https://github.com/rustdev/fastdb"
    assert data["grounding_score"] == 1.0
    assert DemoRun.model_validate(data).candidate.login == "rustdev"


def test_ungrounded_claim_gives_zero_grounding_score():
    from sourcerer.models import Brief, Candidate, Evidence, EvidenceBundle, Claim, Assessment
    from sourcerer.demo.schema import to_demo_run
    cand = Candidate(login="x", profile_url="https://github.com/x")
    bundle = EvidenceBundle(candidate=cand, items=[
        Evidence(source_url="https://github.com/x/r", kind="github_repo", text="t")])
    assessment = Assessment(candidate=cand, fit_score=0.5,
        claims=[Claim(text="ungrounded", citation="https://evil.test")],
        unverified=[], outreach_draft="")
    run = to_demo_run(Brief(role="x", languages=[]), assessment, bundle, [], model="m", generated_at="t")
    assert run.grounding_score == 0.0
