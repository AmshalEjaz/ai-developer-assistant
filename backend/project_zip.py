"""Safe, bounded inspection of project ZIPs without extracting them to disk."""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePosixPath

MAX_ARCHIVE_BYTES = 15 * 1024 * 1024
MAX_ENTRIES = 250
MAX_TOTAL_UNCOMPRESSED = 20 * 1024 * 1024
MAX_MEMBER_BYTES = 300 * 1024
MAX_SELECTED_FILES = 10
MAX_SELECTED_TOTAL_CHARS = 36_000
MAX_FILE_CHARS = 7_000

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
    "build", ".next", "coverage", ".idea", ".vscode", "vendor",
}
SKIP_NAMES = {
    ".env", ".env.local", ".env.production", "id_rsa", "id_ed25519",
    "credentials.json", "secrets.json", "service-account.json",
}
SKIP_SUFFIXES = {
    ".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".exe",
    ".dll", ".so", ".dylib", ".zip", ".7z", ".rar", ".mp4", ".mp3",
    ".woff", ".woff2", ".ttf", ".otf", ".lockb",
}
TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".txt", ".html",
    ".css", ".scss", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".xml",
    ".sql", ".php", ".blade.php", ".sh", ".bat", ".ps1", ".gitignore",
    ".example", ".env.example", ".conf", ".properties", ".java", ".go", ".rs",
    ".c", ".h", ".cpp", ".cs", ".rb", ".vue", ".svelte",
}
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
]


def _eligible(path: str, info: zipfile.ZipInfo) -> bool:
    normalized = path.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if not normalized or normalized.startswith("/") or ".." in parts:
        return False
    if not parts or any(part.lower() in SKIP_DIRS for part in parts):
        return False
    name = parts[-1].lower()
    if name in SKIP_NAMES or name.startswith(".env.") and name != ".env.example":
        return False
    unix_mode = (info.external_attr >> 16) & 0o170000
    if info.is_dir() or unix_mode == 0o120000 or info.file_size > MAX_MEMBER_BYTES or info.flag_bits & 0x1:
        return False
    suffix = PurePosixPath(name).suffix
    if suffix in SKIP_SUFFIXES:
        return False
    return suffix in TEXT_SUFFIXES or name in {"dockerfile", "makefile", ".gitignore", "procfile"}


def _rank(path: str, query: str) -> int:
    lowered = path.lower()
    terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9_]{3,}", query)]
    score = sum(2 for term in terms if term in lowered)
    name = PurePosixPath(lowered).name
    if name in {"readme.md", "package.json", "pyproject.toml", "requirements.txt", "main.py", "app.py"}:
        score += 2
    if any(part in lowered for part in ("src/", "backend/", "frontend/", "app/")):
        score += 1
    return score


def inspect_project_zip(archive_bytes: bytes, question: str) -> dict:
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError("ZIP exceeds the 15 MB upload limit.")
    if not zipfile.is_zipfile(io.BytesIO(archive_bytes)):
        raise ValueError("Please upload a valid .zip project archive.")

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ValueError(f"ZIP contains too many entries (maximum {MAX_ENTRIES}).")
        if sum(info.file_size for info in infos) > MAX_TOTAL_UNCOMPRESSED:
            raise ValueError("ZIP expands beyond the 20 MB safety limit.")

        eligible = [info for info in infos if _eligible(info.filename, info)]
        eligible.sort(key=lambda info: (_rank(info.filename, question), info.filename.lower()), reverse=True)
        chosen = []
        total_chars = 0
        for info in eligible:
            if len(chosen) >= MAX_SELECTED_FILES or total_chars >= MAX_SELECTED_TOTAL_CHARS:
                break
            try:
                raw = archive.read(info)
                text = raw.decode("utf-8-sig")
            except (UnicodeDecodeError, RuntimeError, zipfile.BadZipFile):
                continue
            # Drop lines that look like credentials before any content reaches the model.
            safe_lines = []
            for line in text.splitlines():
                if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                    safe_lines.append("[REDACTED: possible secret]")
                else:
                    safe_lines.append(line)
            content = "\n".join(safe_lines)[:MAX_FILE_CHARS]
            if not content.strip():
                continue
            remaining = MAX_SELECTED_TOTAL_CHARS - total_chars
            content = content[:remaining]
            chosen.append({"path": info.filename, "content": content})
            total_chars += len(content)

    if not chosen:
        raise ValueError("No readable, supported source files found. Secret files, dependencies, binaries, and oversized files are skipped.")
    return {
        "files": chosen,
        "file_count": len(chosen),
        "skipped_count": max(0, len(infos) - len(chosen)),
        "characters_sent": total_chars,
    }


def select_relevant_project_context(context_text: str, question: str) -> str:
    """Select a small subset of a saved project snapshot for one Groq request."""
    text = str(context_text or "")
    if not text:
        return ""
    pattern = re.compile(r"FILE: ([^\n]+)\n```\n(.*?)\n```", re.DOTALL)
    matches = pattern.findall(text)
    if not matches:
        return text[:12_000]
    terms = [term.lower() for term in re.findall(r"[a-zA-Z0-9_]{3,}", question)]
    ranked = []
    asks_for_backend_main = (
        any(term in {"backend", "server", "api"} for term in terms)
        and any(term in {"main", "entry", "primary"} for term in terms)
    )
    for path, content in matches:
        lower_path = path.lower().replace("\\", "/")
        lower_content = content.lower()
        score = sum(3 for term in terms if term in lower_path)
        score += sum(1 for term in set(terms) if term in lower_content)
        name = PurePosixPath(lower_path).name
        if name in {"readme.md", "package.json", "main.py", "app.py"}:
            score += 1
        # When the user asks about the main backend/server file, prefer the real
        # backend entry point over unrelated frontend metadata or config files.
        if asks_for_backend_main and (
            lower_path.endswith("backend/main.py")
            or lower_path.endswith("backend/app.py")
            or lower_path in {"main.py", "app.py", "server.py", "api.py"}
        ):
            score += 100
        ranked.append((score, path, content))
    ranked.sort(key=lambda item: (item[0], item[1].lower()), reverse=True)
    selected = []
    chars = 0
    for _score, path, content in ranked[:3]:
        remaining = 12_000 - chars
        if remaining <= 0:
            break
        content = content[:remaining]
        selected.append(f"FILE: {path}\n```\n{content}\n```")
        chars += len(content)
    return "Relevant excerpts selected from the saved project snapshot. Only these files are in this request context; ask for a more specific file if needed.\n\n" + "\n\n---\n\n".join(selected)
