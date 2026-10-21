from pathlib import Path

import pytest

from file_workspace import (
    allowed_upload_filename,
    conversation_workspace,
    safe_upload_name,
    save_active_file,
    delete_conversation_workspace,
)


@pytest.mark.parametrize("name", [
    r"..\\..\\outside.py",
    "../../outside.py",
    r"C:\\Users\\Public\\outside.py",
    "/tmp/outside.py",
])
def test_upload_filename_strips_cross_platform_path_components(name):
    assert safe_upload_name(name) == "outside.py"


@pytest.mark.parametrize("name", [
    "", ".", "..", "secret.env", ".env", ".env.local",
    "payload.exe", "image.png", "file.py/../../evil.exe",
])
def test_upload_rejects_unsupported_or_empty_names(name):
    assert not allowed_upload_filename(name)


def test_upload_allows_env_example_and_text_code_files():
    assert allowed_upload_filename(".env.example")
    assert allowed_upload_filename("main.py")
    assert allowed_upload_filename("notes.txt")


def test_upload_writes_only_inside_workspace_and_cleans_previous_files(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "old.py").write_text("old", encoding="utf-8")
    external = tmp_path / "external.txt"
    external.write_text("do not delete", encoding="utf-8")
    try:
        (workspace / "external-link").symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not available on this platform")

    result = save_active_file(workspace, r"..\\outside.py", b"print('safe')")
    assert result.parent.resolve() == workspace.resolve()
    assert result.name == "outside.py"
    assert result.read_bytes() == b"print('safe')"
    assert not (workspace / "old.py").exists()
    assert external.read_text(encoding="utf-8") == "do not delete"


def test_upload_rejects_oversized_content(tmp_path):
    from tools import MAX_UPLOAD_BYTES
    with pytest.raises(ValueError, match="2 MB"):
        save_active_file(tmp_path / "workspace", "main.py", b"x" * (MAX_UPLOAD_BYTES + 1))


def test_workspace_is_scoped_by_user_and_conversation(tmp_path):
    a = conversation_workspace(tmp_path, user_id=1, conversation_id=2)
    b = conversation_workspace(tmp_path, user_id=2, conversation_id=2)
    c = conversation_workspace(tmp_path, user_id=1, conversation_id=3)
    assert len({a, b, c}) == 3


def test_delete_workspace_does_not_cross_user_boundary(tmp_path):
    target = conversation_workspace(tmp_path, user_id=1, conversation_id=2)
    target.mkdir(parents=True)
    (target / "code.py").write_text("x", encoding="utf-8")
    other = conversation_workspace(tmp_path, user_id=2, conversation_id=2)
    other.mkdir(parents=True)
    (other / "keep.py").write_text("keep", encoding="utf-8")

    delete_conversation_workspace(tmp_path, user_id=1, conversation_id=2)

    assert not target.parent.exists()
    assert (other / "keep.py").exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
