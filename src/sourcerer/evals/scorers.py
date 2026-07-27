from sourcerer.models import Assessment, EvidenceBundle


def citation_completeness(assessment: Assessment) -> float:
    """Non-vacuous output metric: an empty brief is not a perfectly grounded brief."""
    return 1.0 if assessment.claims else 0.0


def quote_support_score(assessment: Assessment, bundle: EvidenceBundle) -> float:
    """Fraction of claims carrying a verbatim quote present in their cited evidence."""
    if not assessment.claims:
        return 0.0
    evidence = {item.source_url: " ".join(item.text.lower().split()) for item in bundle.items}
    supported = 0
    for claim in assessment.claims:
        quote = " ".join((claim.supporting_quote or "").lower().split())
        supported += bool(quote and quote in evidence.get(claim.citation, ""))
    return supported / len(assessment.claims)


def reciprocal_rank(ranked_logins: list[str], expected_login: str) -> float:
    """Standard retrieval metric used by the offline golden-set runner."""
    try:
        return 1.0 / (ranked_logins.index(expected_login) + 1)
    except ValueError:
        return 0.0


def grounding_score(assessment: Assessment, bundle: EvidenceBundle) -> float:
    if not assessment.claims:
        return 0.0
    urls = bundle.source_urls()
    grounded = sum(1 for c in assessment.claims if c.citation in urls)
    return grounded / len(assessment.claims)


def claims_resolve(assessment: Assessment, bundle: EvidenceBundle) -> bool:
    return grounding_score(assessment, bundle) == 1.0


def model_citation_fidelity(raw_claims: list[dict], valid_urls: set[str]) -> float:
    """Fraction of the model's *asserted* claims (non-empty text + a citation) whose
    citation was actually gathered. Unlike grounding_score, which runs on the already
    fail-closed Assessment and is therefore 1.0 by construction, this is computed over the
    model's RAW output, so it drops below 1.0 exactly when the model fabricates a citation."""
    asserted = [c for c in raw_claims
                if isinstance(c, dict) and c.get("text") and isinstance(c.get("citation"), str) and c["citation"]]
    if not asserted:
        return 1.0
    grounded = sum(1 for c in asserted if c["citation"] in valid_urls)
    return grounded / len(asserted)
