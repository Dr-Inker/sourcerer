from pydantic import BaseModel, Field


class Brief(BaseModel):
    role: str
    languages: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    voice: str = "warm, specific, concise"
    max_candidates: int = 1


class Candidate(BaseModel):
    login: str
    name: str | None = None
    profile_url: str
    signals: dict = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    source_url: str
    kind: str
    text: str


class EvidenceBundle(BaseModel):
    candidate: Candidate
    items: list[Evidence] = Field(default_factory=list)

    def source_urls(self) -> set[str]:
        return {e.source_url for e in self.items}


class Claim(BaseModel):
    text: str
    citation: str


class Assessment(BaseModel):
    candidate: Candidate
    fit_score: float
    claims: list[Claim] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    outreach_draft: str
