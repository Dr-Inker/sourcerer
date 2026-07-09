from sourcerer.models import Assessment, EvidenceBundle


def grounding_score(assessment: Assessment, bundle: EvidenceBundle) -> float:
    if not assessment.claims:
        return 1.0
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
