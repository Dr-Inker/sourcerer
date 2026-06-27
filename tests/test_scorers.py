from sourcerer.evals.scorers import grounding_score, claims_resolve
from sourcerer.models import Candidate, Evidence, EvidenceBundle, Claim, Assessment


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
