from sourcerer.models import Brief, Candidate, Evidence, EvidenceBundle, Claim, Assessment
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
