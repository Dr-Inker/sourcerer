from sourcerer.models import Candidate, Evidence, EvidenceBundle
from sourcerer.github import GitHubClient
from sourcerer.web import Fetcher


async def research(candidate: Candidate, gh: GitHubClient, fetcher: Fetcher) -> EvidenceBundle:
    items: list[Evidence] = []
    for repo in await gh.list_repos(candidate.login, limit=5):
        items.append(Evidence(
            source_url=repo["html_url"], kind="github_repo",
            text=f'{repo["name"]} ({repo.get("language")}, ★{repo.get("stargazers_count",0)}): {repo.get("description") or ""}',
        ))
    blog = candidate.signals.get("blog")
    if blog:
        page = await fetcher.fetch(blog)
        if page:
            items.append(Evidence(source_url=page.url, kind="web_page", text=f"{page.title}: {page.text}"))
    return EvidenceBundle(candidate=candidate, items=items)
