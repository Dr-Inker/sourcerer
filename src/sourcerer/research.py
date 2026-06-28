from sourcerer.models import Candidate, Evidence, EvidenceBundle
from sourcerer.github import GitHubClient
from sourcerer.web import Fetcher
from sourcerer.trace import traced
from sourcerer import ingest


async def _ingest_repo_files(gh: GitHubClient, login: str, repo: dict, budget: list[int]) -> list[Evidence]:
    """Best-effort: README + <=3 notable files for one repo, honoring the shared byte budget."""
    branch = repo.get("default_branch") or "HEAD"
    name = repo["name"]
    try:
        tree = await gh.list_paths(login, name, branch)
    except Exception:
        return []
    targets: list[tuple[str, int]] = []
    readme = ingest.find_readme(tree)
    if readme:
        targets.append((readme, ingest.MAX_README_BYTES))
    for path in ingest.pick_notable(tree):
        targets.append((path, ingest.MAX_FILE_BYTES))

    items: list[Evidence] = []
    for path, cap in targets:
        if budget[0] <= 0:
            break
        try:
            content = await gh.get_file(login, name, path)
        except Exception:
            continue
        if not content:
            continue
        text = ingest.truncate(content, min(cap, budget[0]))
        budget[0] -= len(text.encode("utf-8"))
        items.append(Evidence(
            source_url=ingest.blob_url(repo["html_url"], branch, path),
            kind="github_file", text=text,
        ))
    return items


async def research(candidate: Candidate, gh: GitHubClient, fetcher: Fetcher) -> EvidenceBundle:
    items: list[Evidence] = []
    budget = [ingest.MAX_TOTAL_EVIDENCE_BYTES]
    for repo in await gh.list_repos(candidate.login, limit=5):
        items.append(Evidence(
            source_url=repo["html_url"], kind="github_repo",
            text=f'{repo["name"]} ({repo.get("language")}, ★{repo.get("stargazers_count",0)}): {repo.get("description") or ""}',
        ))
        async with traced("research.files"):
            items.extend(await _ingest_repo_files(gh, candidate.login, repo, budget))
    blog = candidate.signals.get("blog")
    if blog:
        page = await fetcher.fetch(blog)
        if page:
            items.append(Evidence(source_url=page.url, kind="web_page", text=f"{page.title}: {page.text}"))
    return EvidenceBundle(candidate=candidate, items=items)
