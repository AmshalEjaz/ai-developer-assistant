from __future__ import annotations

import shutil
from pathlib import Path

from tools import ALLOWED_TEXT_EXTENSIONS, MAX_UPLOAD_BYTES


SPECIAL_ALLOWED_FILENAMES = {".env.example"}


def allowed_upload_filename(filename: str) -> bool:
    name = Path(str(filename or "")).name
    if not name or name in {".", ".."}:
        return False
    lowered = name.lower()
    if lowered.endswith(".env.example"):
        return True
    return Path(lowered).suffix in ALLOWED_TEXT_EXTENSIONS


def safe_upload_name(filename: str) -> str:
    name = Path(str(filename or "")).name.strip()
    if not allowed_upload_filename(name):
        raise ValueError("Unsupported file type.")
    return name


def conversation_workspace(root: Path, *, user_id: int, conversation_id: int) -> Path:
    root = Path(root).expanduser().resolve()
    return root / f"user_{int(user_id)}" / f"conversation_{int(conversation_id)}" / "active"


def save_active_file(workspace: Path, filename: str, content: bytes) -> Path:
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("File exceeds the 2 MB limit.")
    name = safe_upload_name(filename)
    workspace = Path(workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    for child in workspace.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            shutil.rmtree(child)
    destination = workspace / name
    destination.write_bytes(content)
    return destination


def delete_conversation_workspace(root: Path, *, user_id: int, conversation_id: int) -> None:
    active = conversation_workspace(root, user_id=user_id, conversation_id=conversation_id)
    conversation_dir = active.parent
    if conversation_dir.exists():
        shutil.rmtree(conversation_dir)
