from sourcerer.models import Assessment, EvidenceBundle


def grounding_score(assessment: Assessment, bundle: EvidenceBundle) -> float:
    if not assessment.claims:
        return 1.0
    urls = bundle.source_urls()
    grounded = sum(1 for c in assessment.claims if c.citation in urls)
    return grounded / len(assessment.claims)


def claims_resolve(assessment: Assessment, bundle: EvidenceBundle) -> bool:
    return grounding_score(assessment, bundle) == 1.0
