import json
from sourcerer.synthesis import synthesize, extract_json
from sourcerer.models import Brief, Candidate, Evidence, EvidenceBundle
from sourcerer.llm import MockLLM
def test_extract_json_tolerates_fences_and_prose():
    assert extract_json('ok ```json\n{"a":1}\n``` done') == {"a": 1}
async def test_ungrounded_claim_is_moved_to_unverified():
    cand = Candidate(login="rustdev", name="Rusty", profile_url="https://github.com/rustdev")
    bundle = EvidenceBundle(candidate=cand, items=[Evidence(source_url="https://github.com/rustdev/fastdb", kind="github_repo", text="embedded db")])
    payload = json.dumps({"fit_score": 0.9,
        "claims": [{"text": "Built fastdb", "citation": "https://github.com/rustdev/fastdb"},
                   {"text": "Worked at BigCo", "citation": "https://linkedin.com/in/x"}],
        "unverified": [], "outreach_draft": "Hi Rusty"})
    a = await synthesize(cand, bundle, MockLLM(lambda s, u: payload), model="m")
    assert [c.text for c in a.claims] == ["Built fastdb"]
    assert "Worked at BigCo" in a.unverified
    assert a.fit_score == 0.9
async def test_brief_role_reaches_user_prompt():
    cand = Candidate(login="rustdev", name="Rusty", profile_url="https://github.com/rustdev")
    bundle = EvidenceBundle(candidate=cand, items=[Evidence(source_url="https://github.com/rustdev/fastdb", kind="github_repo", text="embedded db")])
    payload = json.dumps({"fit_score": 0.5, "claims": [], "unverified": [], "outreach_draft": "Hi"})
    llm = MockLLM(lambda s, u: payload)
    brief = Brief(role="Rust systems engineer", languages=["rust"])
    await synthesize(cand, bundle, llm, model="m", brief=brief)
    assert "Rust systems engineer" in llm.calls[0]["user"]
async def test_text_less_grounded_claim_is_skipped():
    cand = Candidate(login="rustdev", name="Rusty", profile_url="https://github.com/rustdev")
    bundle = EvidenceBundle(candidate=cand, items=[Evidence(source_url="https://github.com/rustdev/fastdb", kind="github_repo", text="embedded db")])
    payload = json.dumps({"fit_score": 0.5,
        "claims": [{"text": "", "citation": "https://github.com/rustdev/fastdb"},
                   {"text": "Built fastdb", "citation": "https://github.com/rustdev/fastdb"}],
        "unverified": [], "outreach_draft": "Hi"})
    a = await synthesize(cand, bundle, MockLLM(lambda s, u: payload), model="m")
    assert [c.text for c in a.claims] == ["Built fastdb"]
    assert a.unverified == []


async def test_system_prompt_invites_file_url_citations():
    cand = Candidate(login="x", name="X", profile_url="https://github.com/x")
    bundle = EvidenceBundle(candidate=cand, items=[
        Evidence(source_url="https://github.com/x/r", kind="github_repo", text="r")])
    payload = json.dumps({"fit_score": 0.0, "claims": [], "unverified": [], "outreach_draft": ""})
    llm = MockLLM(lambda s, u: payload)
    await synthesize(cand, bundle, llm, model="m")
    assert "file URL" in llm.calls[0]["system"]


async def test_fabricated_file_path_dropped_real_one_kept():
    cand = Candidate(login="rustdev", name="Rusty", profile_url="https://github.com/rustdev")
    real = "https://github.com/rustdev/fastdb/blob/main/engine.rs"
    bundle = EvidenceBundle(candidate=cand, items=[
        Evidence(source_url=real, kind="github_file", text="fn engine() {}")])
    payload = json.dumps({"fit_score": 0.8, "claims": [
        {"text": "Wrote the storage engine", "citation": real},
        {"text": "Wrote the query planner",
         "citation": "https://github.com/rustdev/fastdb/blob/main/planner.rs"},
    ], "unverified": [], "outreach_draft": "Hi"})
    a = await synthesize(cand, bundle, MockLLM(lambda s, u: payload), model="m")
    assert [c.text for c in a.claims] == ["Wrote the storage engine"]
    assert "Wrote the query planner" in a.unverified
