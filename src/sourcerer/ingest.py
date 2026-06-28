import fnmatch
import posixpath

MAX_TREE_PATHS = 300
FETCH_SIZE_CAP = 64 * 1024
MAX_README_BYTES = 3072
MAX_FILE_BYTES = 1536
MAX_NOTABLE_FILES = 3
MAX_TOTAL_EVIDENCE_BYTES = 12288

BINARY_EXTENSIONS = frozenset({
    "png", "jpg", "jpeg", "gif", "svg", "ico", "bmp", "webp", "pdf", "zip", "gz",
    "tar", "tgz", "bz2", "7z", "rar", "woff", "woff2", "ttf", "eot", "otf", "so",
    "dylib", "dll", "exe", "bin", "wasm", "class", "jar", "mp4", "mp3", "mov",
    "avi", "wav", "flac", "ogg", "webm", "pyc", "o", "a", "lib", "dat", "db", "sqlite",
})
SKIP_DIRS = frozenset({
    "node_modules", "vendor", "dist", "build", "third_party", "deps", ".git",
    "target", ".venv", "__pycache__",
})
SKIP_FILE_PATTERNS = (
    "*.lock", "*-lock.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "*.min.js", "*.min.css",
)


def _ext(path: str) -> str:
    base = posixpath.basename(path)
    dot = base.rfind(".")
    return base[dot + 1:].lower() if dot > 0 else ""


def find_readme(paths: list[dict]) -> str | None:
    for p in paths:
        path = p["path"]
        if "/" not in path and path.lower().startswith("readme"):
            return path
    return None


def decide_file(path: str, size: int) -> str:
    parts = path.split("/")
    if any(d in SKIP_DIRS for d in parts[:-1]):
        return "vendored"
    base = parts[-1]
    if any(fnmatch.fnmatch(base, pat) for pat in SKIP_FILE_PATTERNS):
        return "vendored"
    if _ext(path) in BINARY_EXTENSIONS:
        return "binary"
    if size > FETCH_SIZE_CAP:
        return "too_large"
    return "ok"


def pick_notable(paths: list[dict], max_files: int = MAX_NOTABLE_FILES) -> list[str]:
    readme = find_readme(paths)
    cands = [
        p for p in paths
        if p["path"] != readme and decide_file(p["path"], p.get("size", 0)) == "ok"
    ]
    # root-level first (False<True), then larger first, then path for stable order
    cands.sort(key=lambda p: ("/" in p["path"], -p.get("size", 0), p["path"]))
    return [p["path"] for p in cands[:max_files]]


def blob_url(repo_html_url: str, default_branch: str, path: str) -> str:
    return f"{repo_html_url.rstrip('/')}/blob/{default_branch}/{path}"


def truncate(text: str, max_bytes: int) -> str:
    b = text.encode("utf-8")
    if len(b) <= max_bytes:
        return text
    return b[:max_bytes].decode("utf-8", errors="ignore")
