from sourcerer.github import MockGitHub


async def test_mock_search_and_repos():
    gh = MockGitHub(
        users=[{"login": "rustdev", "name": "Rusty", "html_url": "https://github.com/rustdev", "blog": "https://rusty.dev", "bio": "systems"}],
        repos={"rustdev": [{"name": "fastdb", "language": "Rust", "stargazers_count": 900, "html_url": "https://github.com/rustdev/fastdb", "description": "embedded db"}]},
    )
    assert (await gh.search_users("language:rust", 5))[0]["login"] == "rustdev"
    assert (await gh.list_repos("rustdev", 5))[0]["language"] == "Rust"
