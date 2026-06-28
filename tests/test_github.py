from sourcerer.github import MockGitHub


async def test_mock_search_and_repos():
    gh = MockGitHub(
        users=[{"login": "rustdev", "name": "Rusty", "html_url": "https://github.com/rustdev", "blog": "https://rusty.dev", "bio": "systems"}],
        repos={"rustdev": [{"name": "fastdb", "language": "Rust", "stargazers_count": 900, "html_url": "https://github.com/rustdev/fastdb", "description": "embedded db"}]},
    )
    assert (await gh.search_users("language:rust", 5))[0]["login"] == "rustdev"
    assert (await gh.list_repos("rustdev", 5))[0]["language"] == "Rust"


async def test_mock_list_paths_and_get_file():
    gh = MockGitHub(
        users=[],
        repos={"rustdev": [{"name": "fastdb", "html_url": "https://github.com/rustdev/fastdb", "default_branch": "main"}]},
        trees={"fastdb": [{"path": "README.md", "size": 12}, {"path": "src/a.rs", "size": 30}]},
        files={"fastdb/README.md": "hello"},
    )
    paths = await gh.list_paths("rustdev", "fastdb", "main")
    assert {p["path"] for p in paths} == {"README.md", "src/a.rs"}
    assert await gh.get_file("rustdev", "fastdb", "README.md") == "hello"
    assert await gh.get_file("rustdev", "fastdb", "missing.txt") is None
    # unknown repo -> empty tree, not an error
    assert await gh.list_paths("rustdev", "nope", "main") == []
