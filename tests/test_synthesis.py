import json
from sourcerer.synthesis import synthesize, extract_json
from sourcerer.models import Candidate, Evidence, EvidenceBundle
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
