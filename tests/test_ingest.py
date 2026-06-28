from sourcerer import ingest


def test_find_readme_root_case_insensitive():
    paths = [{"path": "docs/README.md", "size": 10}, {"path": "ReadMe.rst", "size": 10}]
    assert ingest.find_readme(paths) == "ReadMe.rst"


def test_find_readme_absent_returns_none():
    assert ingest.find_readme([{"path": "src/main.py", "size": 10}]) is None


def test_decide_file_reasons():
    assert ingest.decide_file("src/main.py", 100) == "ok"
    assert ingest.decide_file("logo.png", 100) == "binary"
    assert ingest.decide_file("node_modules/x/index.js", 100) == "vendored"
    assert ingest.decide_file("yarn.lock", 100) == "vendored"
    assert ingest.decide_file("app.min.js", 100) == "vendored"
    assert ingest.decide_file("big.py", ingest.FETCH_SIZE_CAP + 1) == "too_large"


def test_pick_notable_excludes_readme_vendored_binary_and_caps():
    paths = [
        {"path": "README.md", "size": 200},
        {"path": "engine.py", "size": 5000},
        {"path": "util.py", "size": 1000},
        {"path": "src/deep.py", "size": 9000},
        {"path": "yarn.lock", "size": 8000},
        {"path": "logo.png", "size": 8000},
    ]
    got = ingest.pick_notable(paths)
    assert "README.md" not in got
    assert "yarn.lock" not in got
    assert "logo.png" not in got
    assert len(got) == 3
    # root-level first (engine.py before util.py by size), then nested deep.py
    assert got == ["engine.py", "util.py", "src/deep.py"]


def test_blob_url_shape():
    assert ingest.blob_url("https://github.com/u/r", "main", "src/a.py") == \
        "https://github.com/u/r/blob/main/src/a.py"
    # trailing slash on repo url is normalized
    assert ingest.blob_url("https://github.com/u/r/", "main", "a.py") == \
        "https://github.com/u/r/blob/main/a.py"


def test_truncate_byte_bound_is_utf8_safe():
    assert ingest.truncate("hello", 100) == "hello"
    out = ingest.truncate("h" * 50, 10)
    assert len(out.encode("utf-8")) <= 10
    # never raises on a multibyte boundary cut
    multi = "é" * 20  # 2 bytes each
    assert len(ingest.truncate(multi, 5).encode("utf-8")) <= 5
