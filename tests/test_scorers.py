from sourcerer.evals.scorers import grounding_score, claims_resolve, model_citation_fidelity
from sourcerer.models import Candidate, Evidence, EvidenceBundle, Claim, Assessment


VALID = {"https://github.com/x/r", "https://github.com/x/r/blob/main/a.py"}


def test_fidelity_all_cited_is_one():
    raw = [{"text": "a", "citation": "https://github.com/x/r"}]
    assert model_citation_fidelity(raw, VALID) == 1.0


def test_fidelity_drops_when_model_fabricates_a_citation():
    # Two asserted claims, one cites a URL never gathered -> the model fabricated it.
    raw = [{"text": "real", "citation": "https://github.com/x/r"},
           {"text": "made up", "citation": "https://github.com/x/r/blob/main/ghost.py"}]
    assert model_citation_fidelity(raw, VALID) == 0.5


def test_fidelity_ignores_empty_text_and_uncited_claims():
    # empty-text or citation-less entries are not assertions of fact, so they don't count.
    raw = [{"text": "", "citation": "https://github.com/x/r"},
           {"text": "no source", "citation": ""},
           {"text": "real", "citation": "https://github.com/x/r"}]
    assert model_citation_fidelity(raw, VALID) == 1.0


def test_fidelity_no_asserted_claims_is_one():
    assert model_citation_fidelity([], VALID) == 1.0


def test_fidelity_ignores_unhashable_citation_without_crashing():
    # A list/dict citation is malformed, not a fabricated URL — it must not crash the set lookup.
    raw = [{"text": "malformed", "citation": ["https://github.com/x/r"]},
           {"text": "real", "citation": "https://github.com/x/r"}]
    assert model_citation_fidelity(raw, VALID) == 1.0


def _bundle():
    c = Candidate(login="x", profile_url="https://github.com/x")
    return c, EvidenceBundle(candidate=c, items=[Evidence(source_url="https://github.com/x/r", kind="github_repo", text="t")])


def test_fully_grounded_scores_one():
    c, b = _bundle()
    a = Assessment(candidate=c, fit_score=0.5, claims=[Claim(text="t", citation="https://github.com/x/r")], unverified=[], outreach_draft="")
    assert grounding_score(a, b) == 1.0 and claims_resolve(a, b) is True


def test_ungrounded_claim_lowers_score():
    c, b = _bundle()
    a = Assessment(candidate=c, fit_score=0.5, claims=[Claim(text="t", citation="https://evil.test")], unverified=[], outreach_draft="")
    assert grounding_score(a, b) == 0.0 and claims_resolve(a, b) is False
