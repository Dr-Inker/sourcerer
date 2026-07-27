from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _public_http_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("expected an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed")
    return value


class Brief(DomainModel):
    role: str = Field(min_length=1, max_length=200)
    languages: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    voice: str = "warm, specific, concise"
    max_candidates: int = Field(default=1, ge=1, le=25)

    @field_validator("languages", "topics", "must_have")
    @classmethod
    def clean_terms(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values if v.strip()]
        if len(cleaned) > 20 or any(len(v) > 100 for v in cleaned):
            raise ValueError("brief terms exceed safe limits")
        return list(dict.fromkeys(cleaned))


class Candidate(DomainModel):
    login: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    name: str | None = None
    profile_url: str
    signals: dict = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)

    @field_validator("profile_url")
    @classmethod
    def validate_profile_url(cls, value: str) -> str:
        return _public_http_url(value)


EvidenceKind = Literal["github_profile", "github_repo", "github_file", "web_page"]


class Evidence(DomainModel):
    source_url: str
    kind: EvidenceKind
    text: str = Field(min_length=1, max_length=20_000)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return _public_http_url(value)


class EvidenceBundle(DomainModel):
    candidate: Candidate
    items: list[Evidence] = Field(default_factory=list)

    def source_urls(self) -> set[str]:
        return {e.source_url for e in self.items}


class Claim(DomainModel):
    text: str = Field(min_length=1, max_length=1_000)
    citation: str
    supporting_quote: str | None = Field(default=None, max_length=1_000)

    @field_validator("citation")
    @classmethod
    def validate_citation(cls, value: str) -> str:
        return _public_http_url(value)


class Assessment(DomainModel):
    candidate: Candidate
    fit_score: float = Field(ge=0.0, le=1.0)
    claims: list[Claim] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    outreach_draft: str = Field(max_length=2_000)
    # Fraction of the model's raw asserted claims whose citation was actually gathered.
    # Drops below 1.0 when the model fabricates a citation (see evals.model_citation_fidelity).
    grounding_fidelity: float | None = None
