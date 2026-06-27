import json
from sourcerer.models import Brief, Candidate, EvidenceBundle, Claim, Assessment
from sourcerer.llm import LLMClient


def extract_json(raw: str) -> dict:
    s = raw.replace("```json", "").replace("```", "").strip()
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1 or b < a:
        raise ValueError("no JSON object in response")
    return json.loads(s[a:b + 1])


def _system(voice: str) -> str:
    return (
        "You assess a software engineer's fit for the SOUGHT ROLE described in the user message, using ONLY the supplied evidence. "
        "For every factual claim you make, cite the exact evidence source_url it comes from. "
        "If you cannot ground a statement in the evidence, put it in 'unverified' — never assert it as a claim. "
        f"Write the outreach in this voice: {voice}. "
        'Respond ONLY with JSON: {"fit_score":<0..1>,"claims":[{"text":"","citation":"<source_url>"}],"unverified":[],"outreach_draft":""}'
    )


async def synthesize(candidate: Candidate, bundle: EvidenceBundle, llm: LLMClient, model: str, brief: Brief | None = None, voice: str = "warm, specific, concise") -> Assessment:
    voice = brief.voice if brief is not None else voice
    ev = "\n".join(f"- [{e.kind}] {e.source_url} :: {e.text}" for e in bundle.items)
    if brief is not None:
        reqs = (f"Sourcing brief — role sought: {brief.role}; "
                f"languages: {', '.join(brief.languages) or 'any'}; "
                f"topics: {', '.join(brief.topics) or 'any'}; "
                f"must-have: {', '.join(brief.must_have) or 'none'}.")
    else:
        reqs = ""
    user = (reqs + "\n" if reqs else "") + f"Candidate: {candidate.name or candidate.login} ({candidate.profile_url})\nEvidence:\n{ev}"
    data = extract_json(await llm.complete(_system(voice), user, model))
    valid_urls = bundle.source_urls()
    claims, unverified = [], list(data.get("unverified", []))
    for c in data.get("claims", []):
        text = c.get("text", "")
        if c.get("citation") in valid_urls:
            if text:
                claims.append(Claim(text=text, citation=c["citation"]))
            # grounded but empty text -> skip (nothing to assert)
        else:
            unverified.append(text)   # empties are filtered out at the end
    score = max(0.0, min(1.0, float(data.get("fit_score", 0.0))))
    return Assessment(candidate=candidate, fit_score=score, claims=claims,
                      unverified=[u for u in unverified if u], outreach_draft=str(data.get("outreach_draft", "")).strip())
