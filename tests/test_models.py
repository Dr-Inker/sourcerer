import pytest
from pydantic import ValidationError

from sourcerer.models import Assessment, Brief, Candidate, Claim, Evidence, EvidenceBundle


def test_bundle_exposes_source_urls():
    c = Candidate(login="octocat", name="Octo", profile_url="https://github.com/octocat")
    b = EvidenceBundle(candidate=c, items=[
        Evidence(source_url="https://github.com/octocat", kind="github_profile", text="bio"),
        Evidence(source_url="https://octo.dev", kind="web_page", text="blog"),
    ])
    assert b.source_urls() == {"https://github.com/octocat", "https://octo.dev"}
def test_assessment_defaults():
    c = Candidate(login="x", name=None, profile_url="https://github.com/x")
    a = Assessment(candidate=c, fit_score=0.8, claims=[Claim(text="ships Rust", citation="https://github.com/x")], unverified=[], outreach_draft="hi")
    assert a.fit_score == 0.8 and a.claims[0].citation == "https://github.com/x"


def test_brief_rejects_invalid_candidate_limits_and_unknown_fields():
    with pytest.raises(ValidationError):
        Brief(role="x", max_candidates=0)
    with pytest.raises(ValidationError):
        Brief(role="x", surprise=True)


def test_assessment_score_is_constrained():
    c = Candidate(login="x", profile_url="https://github.com/x")
    with pytest.raises(ValidationError):
        Assessment(candidate=c, fit_score=1.1, outreach_draft="")


def test_domain_urls_reject_non_http_and_embedded_credentials():
    with pytest.raises(ValidationError):
        Candidate(login="x", profile_url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        Evidence(source_url="https://user:secret@example.com/x", kind="web_page", text="x")
