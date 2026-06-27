from sourcerer.models import Brief, Candidate
from sourcerer.github import GitHubClient


def build_query(brief: Brief) -> str:
    parts = [f"language:{lang}" for lang in brief.languages]
    parts += brief.topics
    parts.append("type:user")
    return " ".join(parts)


async def discover(brief: Brief, gh: GitHubClient) -> list[Candidate]:
    users = await gh.search_users(build_query(brief), brief.max_candidates)
    out: list[Candidate] = []
    for u in users:
        out.append(Candidate(
            login=u["login"], name=u.get("name"), profile_url=u["html_url"],
            signals={"followers": u.get("followers"), "blog": u.get("blog") or None, "bio": u.get("bio")},
            sources=[u["html_url"]],
        ))
    return out
