from pydantic import BaseModel
from sourcerer.models import Brief, Assessment, EvidenceBundle
from sourcerer.evals.scorers import grounding_score


class DemoClaim(BaseModel):
    text: str
    citation: str


class DemoEvidence(BaseModel):
    kind: str
    source_url: str
    text: str


class DemoSpan(BaseModel):
    name: str
    ms: float
    ok: bool


class DemoCandidate(BaseModel):
    login: str
    name: str | None = None
    profile_url: str


class DemoRun(BaseModel):
    role: str
    languages: list[str]
    candidate: DemoCandidate
    fit_score: float
    grounding_score: float
    claims: list[DemoClaim]
    unverified: list[str]
    outreach_draft: str
    evidence: list[DemoEvidence]
    spans: list[DemoSpan]
    model: str
    generated_at: str


def _dedupe_claims(claims: list) -> list[DemoClaim]:
    """Keep the first occurrence of each unique claim text (the LLM sometimes repeats a claim)."""
    seen: set[str] = set()
    out: list[DemoClaim] = []
    for c in claims:
        if c.text in seen:
            continue
        seen.add(c.text)
        out.append(DemoClaim(text=c.text, citation=c.citation))
    return out


def to_demo_run(brief: Brief, assessment: Assessment, bundle: EvidenceBundle,
                spans: list[dict], model: str, generated_at: str) -> DemoRun:
    return DemoRun(
        role=brief.role,
        languages=list(brief.languages),
        candidate=DemoCandidate(
            login=assessment.candidate.login,
            name=assessment.candidate.name,
            profile_url=assessment.candidate.profile_url,
        ),
        fit_score=assessment.fit_score,
        grounding_score=grounding_score(assessment, bundle),
        claims=_dedupe_claims(assessment.claims),
        unverified=list(assessment.unverified),
        outreach_draft=assessment.outreach_draft,
        evidence=[DemoEvidence(kind=e.kind, source_url=e.source_url, text=e.text)
                  for e in bundle.items],
        spans=[DemoSpan(name=s["name"], ms=s["ms"], ok=s["ok"]) for s in spans],
        model=model,
        generated_at=generated_at,
    )
