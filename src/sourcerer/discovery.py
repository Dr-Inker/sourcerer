import re
import sys

import httpx

from sourcerer.github import GitHubClient
from sourcerer.models import Brief, Candidate


def build_query(brief: Brief) -> str:
    # GitHub user search is a recall-oriented first stage. Include the actual role and hard
    # requirements; previously two briefs with different roles produced the same query.
    def term(value: str) -> str:
        value = re.sub(r"[^\w.+# -]", " ", value).strip()
        return f'"{value}"' if " " in value else value

    parts = [term(brief.role)]
    parts += [f"language:{term(lang)}" for lang in brief.languages]
    parts += [term(value) for value in (*brief.topics, *brief.must_have)]
    parts.append("type:user")
    # GitHub caps search queries at 256 characters. Fail predictably rather than relying on an
    # opaque API 422, while preserving the role and qualifiers at the front.
    return " ".join(parts)[:256].rstrip()


def _relevance(user: dict, brief: Brief) -> tuple[float, int]:
    haystack = " ".join(str(user.get(k) or "") for k in ("login", "name", "bio")).lower()
    requirements = [brief.role, *brief.languages, *brief.topics, *brief.must_have]
    words = {w.lower() for value in requirements for w in re.findall(r"[\w+#.]{3,}", value)}
    matched = sum(word in haystack for word in words)
    coverage = matched / len(words) if words else 0.0
    return coverage, int(user.get("followers") or 0)


async def discover(brief: Brief, gh: GitHubClient) -> list[Candidate]:
    try:
        # Fetch a modest recall pool, then deterministically rerank full profiles against the
        # complete brief. GitHub's ordering alone is not a candidate-fit score.
        pool_size = min(100, max(brief.max_candidates, brief.max_candidates * 5))
        users = await gh.search_users(build_query(brief), pool_size)
    except httpx.HTTPError as e:
        # Search failing (rate-limit, network) yields no candidates rather than a traceback.
        print(f"warning: candidate search failed: {e!r}", file=sys.stderr)
        return []
    out: list[Candidate] = []
    users = sorted(users, key=lambda u: _relevance(u, brief), reverse=True)[:brief.max_candidates]
    for u in users:
        relevance, _ = _relevance(u, brief)
        out.append(Candidate(
            login=u["login"], name=u.get("name"), profile_url=u["html_url"],
            signals={"followers": u.get("followers"), "blog": u.get("blog") or None,
                     "bio": u.get("bio"), "discovery_score": relevance},
            sources=[u["html_url"]],
        ))
    return out
